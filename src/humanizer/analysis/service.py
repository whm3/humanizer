from __future__ import annotations

from contextvars import copy_context
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from time import perf_counter
from uuid import uuid4

from humanizer.analysis.profiles import get_profile
from humanizer.api.schemas import (
    AnalysisSummary,
    AggregateSummary,
    AnalyzeAggregateResult,
    AnalyzeRequest,
    AnalyzeResult,
    BatchAnalyzeItemResponse,
    HumanizeIteration,
    HumanizeRequest,
    HumanizeResult,
)
from humanizer.core.errors import ValidationError
from humanizer.core.errors import ProviderTransientError
from humanizer.core.settings import Settings
from humanizer.core.token_usage import TokenUsageLogger
from humanizer.input_loading import detect_content_type, resolve_text_input
from humanizer.providers.base import (
    ProviderAdapter,
    ProviderRequest,
    RewriteRequest,
    RewriteReviewRequest,
)


logger = logging.getLogger(__name__)
SECTION_REWRITE_MAX_CHARS = 3500


@dataclass
class RewriteOutcome:
    text: str
    status: str
    rejection_reason: str | None = None
    candidates: list[dict[str, object]] = field(default_factory=list)


class AnalysisService:
    def __init__(self, settings: Settings, providers: dict[str, ProviderAdapter]):
        self.settings = settings
        self.providers = providers
        self._rewrite_review_cache: dict[tuple[str, str, str], bool] = {}
        self.token_usage_logger = TokenUsageLogger(
            path=settings.token_usage_log_path,
            enabled=settings.token_usage_log_enabled,
        )

    def analyze(self, request: AnalyzeRequest) -> AnalyzeAggregateResult:
        input_text = resolve_text_input(request.text, request.input_path, request.input_url)
        content_type = detect_content_type(input_text, request.input_path, request.content_type)
        if len(input_text) > self.settings.request_text_max_chars:
            raise ValidationError("text exceeds configured limit")
        profile = get_profile(request.profile)
        selected_providers = self._resolve_providers(request, profile.supported_providers)
        available_override = request.metadata.get("_available_providers")
        if isinstance(available_override, list) and request.provider is None:
            selected_providers = [
                provider_name
                for provider_name in selected_providers
                if provider_name in available_override
            ]
        if not selected_providers:
            raise ValidationError("no enabled providers with configured credentials are available")
        logger.debug(
            "analyze.start profile=%s content_type=%s requested_provider=%s selected_providers=%s",
            request.profile,
            content_type,
            request.provider,
            ",".join(selected_providers),
        )

        started = perf_counter()
        source_results: list[AnalyzeResult] = []
        transient_failures: list[str] = []
        with ThreadPoolExecutor(max_workers=min(len(selected_providers), 5) or 1) as executor:
            futures = {
                executor.submit(
                    copy_context().run,
                    self._analyze_with_provider,
                    provider_name,
                    request,
                    input_text,
                    content_type,
                    profile.name,
                    profile.system_prompt,
                ): provider_name
                for provider_name in selected_providers
            }
            for future in as_completed(futures):
                provider_name = futures[future]
                try:
                    source_results.append(future.result())
                except ProviderTransientError:
                    if request.provider is not None:
                        raise
                    transient_failures.append(provider_name)
                    logger.warning("analyze.provider_unavailable provider=%s", provider_name)
        if not source_results:
            if transient_failures:
                raise ValidationError(
                    "all selected providers were temporarily unavailable for this request"
                )
            raise ValidationError("no enabled providers with configured credentials are available")
        latency_ms = max(1, int((perf_counter() - started) * 1000))
        consensus = self._build_consensus(source_results)
        worst_case = max(source_results, key=lambda result: result.score)
        logger.debug(
            "analyze.done profile=%s consensus_label=%s consensus_score=%.4f providers=%s",
            profile.name,
            consensus.label,
            consensus.score,
            ",".join(result.provider for result in source_results),
        )

        source_results.sort(key=lambda result: result.provider)
        return AnalyzeAggregateResult(
            content_type=content_type,
            profile=profile.name,
            request_id=f"req_{uuid4().hex[:12]}",
            latency_ms=latency_ms,
            provider_selection=request.provider or "all_available",
            selected_providers=[result.provider for result in source_results],
            source_results=source_results,
            consensus=consensus,
            worst_case=worst_case,
            summary=self._build_summary(profile.name, content_type, source_results, consensus, worst_case),
        )

    def analyze_batch(self, items: list[AnalyzeRequest]) -> list[BatchAnalyzeItemResponse]:
        if len(items) > self.settings.batch_max_items:
            raise ValidationError("batch exceeds configured limit")

        results: list[BatchAnalyzeItemResponse] = []
        for item in items:
            try:
                results.append(BatchAnalyzeItemResponse(status="success", result=self.analyze(item)))
            except ValidationError as exc:
                results.append(BatchAnalyzeItemResponse(status="error", error=str(exc)))
        return results

    def humanize_until_threshold(self, request: HumanizeRequest) -> HumanizeResult:
        current_text = resolve_text_input(request.text, request.input_path, request.input_url)
        content_type = detect_content_type(current_text, request.input_path, request.content_type)
        if content_type == "code":
            raise ValidationError("humanization is disabled for source code inputs")
        humanizer_provider, humanizer_model = self._resolve_humanizer(request)
        profile = get_profile(request.profile)
        requested_detection_providers = self._resolve_providers(
            AnalyzeRequest(
                text=current_text,
                content_type=content_type,
                profile=request.profile,
                provider=request.provider,
                model=request.model,
                fast_mode=request.fast_mode,
                language_hint=request.language_hint,
                metadata=request.metadata,
            ),
            profile.supported_providers,
        )
        available_detection_providers = self._preflight_available_providers(
            requested_detection_providers,
            content_type,
            request.language_hint,
        )
        logger.debug(
            "humanize.start profile=%s provider=%s model=%s threshold=%.2f max_iterations=%d",
            request.profile,
            humanizer_provider,
            humanizer_model,
            request.threshold,
            request.max_iterations,
        )
        iterations: list[HumanizeIteration] = []
        final_analysis: AnalyzeAggregateResult | None = None

        for iteration_index in range(1, request.max_iterations + 1):
            analysis = self.analyze(
                AnalyzeRequest(
                    text=current_text,
                    content_type=content_type,
                    profile=request.profile,
                    provider=request.provider,
                    model=request.model,
                    fast_mode=request.fast_mode,
                    language_hint=request.language_hint,
                    metadata={**request.metadata, "_available_providers": available_detection_providers},
                )
            )
            final_analysis = analysis
            if analysis.consensus.score <= request.threshold:
                iterations.append(
                    HumanizeIteration(
                        iteration=iteration_index,
                        input_text=current_text,
                        output_text=current_text,
                        applied_changes=[],
                        rewrite_status="skipped",
                        rewrite_rejection_reason=None,
                        candidate_rewrites=[],
                        analysis=analysis,
                    )
                )
                break

            # Use ALL configured providers for review, not just analysis providers.
            # This ensures cross-validation works even when analysis is pinned to one provider.
            all_provider_names = sorted(self.providers.keys())
            rewrite_outcome = self._rewrite_text(
                current_text,
                analysis.summary.humanization_changes,
                analysis.consensus.signals,
                all_provider_names,
                humanizer_provider,
                humanizer_model,
                request.language_hint,
                iteration_index,
                analysis.consensus.score,
                request.threshold,
                request.fast_mode,
                request.max_rewrite_sections,
            )
            iterations.append(
                HumanizeIteration(
                    iteration=iteration_index,
                    input_text=current_text,
                    output_text=rewrite_outcome.text,
                    applied_changes=analysis.summary.humanization_changes,
                    rewrite_status=rewrite_outcome.status,
                    rewrite_rejection_reason=rewrite_outcome.rejection_reason,
                    candidate_rewrites=rewrite_outcome.candidates if self._debug_enabled() else [],
                    analysis=analysis,
                )
            )
            current_text = rewrite_outcome.text
            logger.debug(
                "humanize.iteration iteration=%d prior_score=%.4f rewrite_status=%s rewritten_changed=%s",
                iteration_index,
                analysis.consensus.score,
                rewrite_outcome.status,
                rewrite_outcome.text.strip() != iterations[-1].input_text.strip(),
            )

        if final_analysis is None:
            raise ValidationError("humanization did not produce an analysis result")

        if iterations and iterations[-1].output_text != current_text:
            current_text = iterations[-1].output_text

        if final_analysis.consensus.score > request.threshold:
            available_providers = self._preflight_available_providers(
                final_analysis.selected_providers,
                content_type,
                request.language_hint,
            )
            final_analysis = self.analyze(
                AnalyzeRequest(
                    text=current_text,
                    content_type=content_type,
                    profile=request.profile,
                    provider=request.provider,
                    model=request.model,
                    fast_mode=request.fast_mode,
                    language_hint=request.language_hint,
                    metadata={**request.metadata, "_available_providers": available_providers},
                )
            )

        return HumanizeResult(
            original_text=resolve_text_input(request.text, request.input_path, request.input_url),
            rewritten_text=current_text,
            threshold=request.threshold,
            humanizer_provider=humanizer_provider,
            humanizer_model=humanizer_model,
            reached_threshold=final_analysis.consensus.score <= request.threshold,
            iterations=iterations,
            final_analysis=final_analysis,
        )

    def list_providers(self) -> list[dict[str, str | bool]]:
        return [
            {
                "name": provider_name,
                "enabled": True,
                "default_model": self.providers[provider_name].default_model,
            }
            for provider_name in sorted(self.providers)
        ]

    def provider_status(self) -> list[dict[str, str | bool]]:
        """Report provider configuration status without making billable API calls.

        This is a configuration check, not a live availability probe. Providers
        are listed as available if they have API keys configured. Actual provider
        health is tested when real analyze/rewrite calls are made.
        """
        statuses: list[dict[str, str | bool]] = []
        for provider_name in sorted(self.providers):
            provider = self.providers[provider_name]
            statuses.append(
                {
                    "name": provider_name,
                    "available": True,
                    "default_model": provider.default_model,
                    "detail": "configured",
                }
            )
        return statuses

    def _resolve_providers(
        self,
        request: AnalyzeRequest,
        supported_providers: tuple[str, ...],
    ) -> list[str]:
        if request.provider is not None:
            if request.provider not in self.providers:
                raise ValidationError(f"unsupported or disabled provider: {request.provider}")
            if request.provider not in supported_providers:
                raise ValidationError(
                    f"profile {request.profile} does not support provider: {request.provider}"
                )
            return [request.provider]

        provider_names = [
            provider_name
            for provider_name in sorted(self.providers)
            if provider_name in supported_providers
        ]
        if request.fast_mode:
            return self._limit_fast_mode_providers(provider_names)
        return provider_names

    def _resolve_humanizer(self, request: HumanizeRequest) -> tuple[str, str]:
        provider_name = request.humanizer_provider or self.settings.default_humanizer_provider
        if provider_name not in self.providers:
            raise ValidationError(f"unsupported or disabled humanizer provider: {provider_name}")
        model_name = request.humanizer_model or self.providers[provider_name].default_model
        logger.debug("humanizer.resolve provider=%s model=%s", provider_name, model_name)
        return provider_name, model_name

    def _analyze_with_provider(
        self,
        provider_name: str,
        request: AnalyzeRequest,
        input_text: str,
        content_type: str,
        profile_name: str,
        system_prompt: str,
    ) -> AnalyzeResult:
        model = request.model or self.providers[provider_name].default_model
        started = perf_counter()
        provider_result = self.providers[provider_name].analyze(
            ProviderRequest(
                text=input_text,
                profile_name=profile_name,
                language_hint=request.language_hint,
                content_type=content_type,
                system_prompt=system_prompt,
                model=model,
                metadata=request.metadata,
            )
        )
        latency_ms = max(1, int((perf_counter() - started) * 1000))
        return AnalyzeResult(
            provider=provider_name,
            model=model,
            profile=profile_name,
            label=provider_result.label,
            score=provider_result.score,
            confidence=provider_result.confidence,
            signals=provider_result.signals,
            explanation=provider_result.explanation,
            request_id=f"req_{uuid4().hex[:12]}",
            latency_ms=latency_ms,
        )

    def _build_consensus(self, source_results: list[AnalyzeResult]) -> AggregateSummary:
        average_score = round(
            sum(result.score for result in source_results) / max(len(source_results), 1),
            4,
        )
        labels = [result.label for result in source_results]
        if len(set(labels)) == 1:
            label = labels[0]
        else:
            # Profile-aware consensus: use the actual labels from results,
            # not hardcoded ai_detection labels. Count votes for whichever
            # label appears most, breaking ties toward the higher-scoring label.
            from humanizer.providers.json_utils import POSITIVE_LABELS, PROFILE_LABELS
            profile_name = source_results[0].profile if source_results else "ai_detection"
            positive_label = POSITIVE_LABELS.get(profile_name, "likely_ai_assisted")
            allowed = PROFILE_LABELS.get(profile_name, {"likely_ai_assisted", "likely_human"})
            negative_label = (allowed - {positive_label}).pop() if len(allowed) == 2 else "likely_human"
            positive_votes = sum(1 for lbl in labels if lbl == positive_label)
            label = positive_label if positive_votes >= (len(labels) / 2) else negative_label
        confidence = "high" if len(set(labels)) == 1 and len(labels) > 1 else "medium"
        signals: list[str] = []
        for result in source_results:
            for signal in result.signals:
                if signal not in signals:
                    signals.append(signal)

        return AggregateSummary(
            label=label,
            score=average_score,
            confidence=confidence,
            signals=signals[:4],
            providers_considered=[result.provider for result in source_results],
        )

    def _build_summary(
        self,
        profile_name: str,
        content_type: str,
        source_results: list[AnalyzeResult],
        consensus: AggregateSummary,
        worst_case: AnalyzeResult,
    ) -> AnalysisSummary:
        providers = ", ".join(result.provider for result in source_results)
        evidence = ", ".join(consensus.signals[:3]) or "limited provider evidence"
        detections = (
            f"{len(source_results)} sources analyzed via {providers}. "
            f"Consensus label is {consensus.label} with score {consensus.score:.2f}. "
            f"Worst-case source is {worst_case.provider} at score {worst_case.score:.2f}."
        )
        trends = (
            "Providers broadly agree on the main structural signals."
            if consensus.confidence == "high"
            else "Providers show mixed signals but point to overlapping structural patterns."
        )
        if "human" in consensus.label or consensus.label == "naturally_varied":
            ai_evidence = (
                f"Primary evidence supporting the classification: {evidence}. "
                f"Highest-scoring source: {worst_case.provider} reported {worst_case.label}."
            )
        else:
            ai_evidence = (
                f"Primary evidence of AI involvement: {evidence}. "
                f"Highest-risk source: {worst_case.provider} reported {worst_case.label}."
            )
        if content_type == "code":
            humanization_changes = []
            humanization = "Humanization is disabled for source code inputs."
        else:
            humanization_changes = self._humanization_changes(profile_name, consensus.signals)
            humanization = (
                "To make the output feel more human, reduce the strongest repeated signals and "
                f"focus on these changes: {', '.join(humanization_changes)}."
            )
        return AnalysisSummary(
            detections=detections,
            trends=trends,
            ai_evidence=ai_evidence,
            humanization=humanization,
            humanization_changes=humanization_changes,
        )

    def _humanization_changes(self, profile_name: str, signals: list[str]) -> list[str]:
        changes: list[str] = []
        signal_text = " ".join(signals).lower()
        if "regularity" in signal_text:
            changes.append("vary sentence length and structure")
        if "dense" in signal_text or "rhythm" in signal_text:
            changes.append("break up dense passages with shorter, uneven phrasing")
        if "lexical" in signal_text:
            changes.append("use more specific and less repetitive word choices")
        if "fictional" in signal_text or "technobabble" in signal_text or "invented" in signal_text:
            changes.append("replace invented terminology with plain, credible language")
        if "bibliography" in signal_text or "citations" in signal_text or "references" in signal_text:
            changes.append("remove fabricated citations and unsupported references")
        if "whitepaper" in signal_text or "formal" in signal_text or "structured" in signal_text:
            changes.append("soften overly rigid whitepaper structure and reduce boilerplate formality")
        if "numeric" in signal_text or "precision" in signal_text or "specifics" in signal_text:
            changes.append("reduce implausible numeric precision unless the exact values matter")
        if "generic" in signal_text or "abstract" in signal_text or "platitudes" in signal_text:
            changes.append("replace generic rhetoric with plainer, more concrete language")
        if "patriotic" in signal_text or "persuasive" in signal_text or "rhetorical" in signal_text:
            changes.append("dial back speechwriter-style rhetoric and make the voice less ceremonial")
        if "parallel" in signal_text or "repetitive" in signal_text or "motivational" in signal_text:
            changes.append("break up repeated motivational phrasing and avoid tidy rhetorical contrasts")
        if profile_name == "humanization_feedback":
            changes.append("add personal perspective or lived-detail phrasing")
        if not changes:
            changes.append("introduce more varied cadence and concrete detail")
        return changes[:4]

    def _rewrite_text(
        self,
        text: str,
        changes: list[str],
        signals: list[str],
        review_provider_names: list[str],
        humanizer_provider: str,
        humanizer_model: str,
        language_hint: str,
        iteration_index: int,
        prior_score: float,
        target_score: float,
        fast_mode: bool,
        max_rewrite_sections: int | None,
    ) -> RewriteOutcome:
        segments = text.split("```")
        rewritten_segments: list[str] = []
        all_candidates: list[dict[str, object]] = []
        any_accepted = False
        any_rejected = False
        rejection_reasons: list[str] = []
        rewrite_review_providers = self._select_rewrite_review_providers(
            review_provider_names,
            humanizer_provider,
            fast_mode,
        )
        rewrite_brief = self._build_rewrite_brief(text, changes, signals)
        remaining_sections = max_rewrite_sections
        for index, segment in enumerate(segments):
            if index % 2 == 1:
                rewritten_segments.append(f"```{segment}```")
                continue
            prose_sections = self._split_rewrite_sections(segment)
            if len(prose_sections) <= 1:
                if remaining_sections is not None and remaining_sections <= 0:
                    rewritten_segments.append(segment)
                    continue
                outcome = self._rewrite_prose_segment(
                        segment,
                        changes,
                        signals,
                        rewrite_review_providers,
                        humanizer_provider,
                        humanizer_model,
                        language_hint,
                        iteration_index,
                        prior_score,
                        target_score,
                        fast_mode,
                        rewrite_brief,
                        0,
                        1,
                    )
                rewritten_segments.append(outcome.text)
                if remaining_sections is not None:
                    remaining_sections -= 1
                all_candidates.extend(outcome.candidates)
                any_accepted = any_accepted or outcome.status == "accepted"
                any_rejected = any_rejected or outcome.status == "rejected"
                if outcome.rejection_reason:
                    rejection_reasons.append(outcome.rejection_reason)
                continue
            if remaining_sections is not None:
                sections_to_rewrite = prose_sections[:remaining_sections]
                sections_to_preserve = prose_sections[remaining_sections:]
            else:
                sections_to_rewrite = prose_sections
                sections_to_preserve = []
            if not sections_to_rewrite:
                rewritten_segments.append(segment)
                continue
            rewritten_sections = [
                self._rewrite_prose_segment(
                    prose_section,
                    changes,
                    signals,
                    rewrite_review_providers,
                    humanizer_provider,
                    humanizer_model,
                    language_hint,
                    iteration_index,
                    prior_score,
                    target_score,
                    fast_mode,
                    rewrite_brief,
                    section_index,
                    len(sections_to_rewrite),
                )
                for section_index, prose_section in enumerate(sections_to_rewrite)
            ]
            combined_sections = [item.text for item in rewritten_sections] + sections_to_preserve
            rewritten_segments.append(self._smooth_rewritten_sections(combined_sections))
            if remaining_sections is not None:
                remaining_sections = max(0, remaining_sections - len(sections_to_rewrite))
            for outcome in rewritten_sections:
                all_candidates.extend(outcome.candidates)
                any_accepted = any_accepted or outcome.status == "accepted"
                any_rejected = any_rejected or outcome.status == "rejected"
                if outcome.rejection_reason:
                    rejection_reasons.append(outcome.rejection_reason)
        status = "accepted" if any_accepted else ("rejected" if any_rejected else "unchanged")
        rejection_reason = "; ".join(dict.fromkeys(rejection_reasons)) or None
        final_text = "".join(rewritten_segments)
        return RewriteOutcome(
            text=final_text,
            status=status,
            rejection_reason=rejection_reason,
            candidates=all_candidates if self._debug_enabled() else [],
        )

    def _rewrite_prose_segment(
        self,
        text: str,
        changes: list[str],
        signals: list[str],
        review_provider_names: list[str],
        humanizer_provider: str,
        humanizer_model: str,
        language_hint: str,
        iteration_index: int,
        prior_score: float,
        target_score: float,
        fast_mode: bool,
        rewrite_brief: str,
        section_index: int,
        section_total: int,
    ) -> RewriteOutcome:
        if not text.strip():
            return RewriteOutcome(text=text, status="unchanged")
        candidates: list[dict[str, object]] = []
        rewritten = self.providers[humanizer_provider].rewrite(
            RewriteRequest(
                text=text,
                language_hint=language_hint,
                content_type="text",
                model=humanizer_model,
                changes=changes,
                signals=signals,
                iteration=iteration_index,
                prior_score=prior_score,
                target_score=target_score,
                metadata={
                    "rewrite_brief": rewrite_brief,
                    "section_index": section_index,
                    "section_total": section_total,
                },
            )
        )
        self._record_candidate(candidates, "provider", rewritten)
        if not rewritten.strip():
            rewritten = text
        guarded, rejection_reason = self._apply_rewrite_guardrails(
            text,
            rewritten,
            review_provider_names,
            language_hint,
        )
        self._record_candidate(candidates, "guarded", guarded, rejection_reason)
        if (
            guarded.strip() == text.strip()
            and prior_score > (target_score + 0.20)
        ):
            fallback = self._apply_safe_fallback_rewrite(text, changes, signals)
            if fallback.strip() != text.strip():
                self._record_candidate(candidates, "fallback", fallback)
                guarded, fallback_reason = self._apply_rewrite_guardrails(
                    text,
                    fallback,
                    review_provider_names,
                    language_hint,
                )
                self._record_candidate(candidates, "fallback_guarded", guarded, fallback_reason)
                if fallback_reason and not rejection_reason:
                    rejection_reason = fallback_reason
        if guarded.strip() == text.strip():
            status = "rejected" if rejection_reason else "unchanged"
            return RewriteOutcome(
                text=text,
                status=status,
                rejection_reason=rejection_reason,
                candidates=candidates if self._debug_enabled() else [],
            )
        return RewriteOutcome(
            text=guarded,
            status="accepted",
            rejection_reason=None,
            candidates=candidates if self._debug_enabled() else [],
        )

    def _apply_rewrite_guardrails(
        self,
        original_text: str,
        rewritten_text: str,
        review_provider_names: list[str],
        language_hint: str,
    ) -> tuple[str, str | None]:
        sanitized = rewritten_text
        rejection_reason: str | None = None

        if not _contains_citation_markers(original_text):
            sanitized = _strip_citation_markers(sanitized)
        if not _contains_urls(original_text):
            sanitized = _strip_urls(sanitized)
        if not _contains_reference_heading(original_text):
            sanitized = _strip_reference_sections(sanitized)

        if sanitized.strip() == original_text.strip():
            return original_text, "guardrails removed unsupported additions or no material change remained"

        # Deterministic factual-novelty check: reject rewrites that introduce
        # numbers, dates, percentages, or dollar amounts not in the original.
        novel_facts = _detect_novel_facts(original_text, sanitized)
        if novel_facts:
            logger.warning(
                "rewrite.novel_facts_detected count=%d examples=%s",
                len(novel_facts), novel_facts[:3],
            )
            return original_text, f"rewrite introduced {len(novel_facts)} novel factual element(s): {', '.join(novel_facts[:3])}"

        if not review_provider_names:
            # No alternate provider to validate the rewrite. Instead of hard-rejecting,
            # accept the rewrite with a warning. The caller can check for this reason.
            logger.warning("rewrite.no_reviewer accepting rewrite without cross-validation")
            return sanitized.strip() or original_text, None

        if not self._rewrite_has_provider_consensus(
            original_text,
            sanitized,
            review_provider_names,
            language_hint,
        ):
            rejection_reason = "alternate provider validation rejected the rewrite"
            logger.debug("rewrite.rejected reason=%s", rejection_reason)
            return original_text, rejection_reason

        return sanitized.strip() or original_text, None

    def _select_rewrite_review_providers(
        self,
        provider_names: list[str],
        humanizer_provider: str,
        fast_mode: bool,
    ) -> list[str]:
        review_providers = [
            provider_name for provider_name in provider_names if provider_name != humanizer_provider
        ]
        if fast_mode:
            return review_providers[:1]
        return review_providers

    def _build_rewrite_brief(
        self,
        text: str,
        changes: list[str],
        signals: list[str],
    ) -> str:
        opening = _first_meaningful_paragraph(text)
        brief_lines = [
            "Apply the same voice and terminology rules consistently across every rewritten section.",
            "Prefer the same overall level of formality throughout the document; do not let sections drift apart in tone.",
            "CRITICAL: Only restyle existing sentences. Do NOT add new factual claims, statistics, dates, "
            "standard references, or named examples that are not in the original text. Do NOT remove factual "
            "claims from the original. The rewrite must preserve the same informational content — only the "
            "voice, sentence structure, and word choice should change.",
        ]
        if opening:
            brief_lines.append(f"Anchor the document voice to this representative passage: {opening}")
        if changes:
            brief_lines.append("Primary global rewrite goals: " + "; ".join(changes[:3]))
        if signals:
            brief_lines.append("Global detector artifacts to reduce: " + "; ".join(signals[:3]))
        return "\n".join(brief_lines)

    def _split_rewrite_sections(self, text: str) -> list[str]:
        if len(text) <= SECTION_REWRITE_MAX_CHARS:
            return [text]
        blocks = _split_markdown_blocks(text)
        sections: list[str] = []
        current = ""
        for block in blocks:
            if not block.strip():
                if current:
                    current += block
                continue
            if current and (
                len(current) + len(block) > SECTION_REWRITE_MAX_CHARS
                or _starts_new_natural_section(block)
            ):
                sections.append(current)
                current = block
            else:
                current += block
        if current:
            sections.append(current)
        return [section for section in sections if section.strip()] or [text]

    def _smooth_rewritten_sections(self, sections: list[str]) -> str:
        cleaned: list[str] = []
        for section in sections:
            section_text = section.strip()
            if not section_text:
                continue
            if cleaned:
                previous = cleaned[-1]
                previous_words = previous.split()
                section_words = section_text.split()
                overlap = 0
                max_overlap = min(len(previous_words), len(section_words), 16)
                for size in range(max_overlap, 3, -1):
                    if previous_words[-size:] == section_words[:size]:
                        overlap = size
                        break
                if overlap:
                    section_text = " ".join(section_words[overlap:]).strip()
            if section_text:
                cleaned.append(section_text)
        joined = "\n\n".join(cleaned)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        joined = re.sub(r"[ \t]{2,}", " ", joined)
        return joined.strip()

    def _limit_fast_mode_providers(self, provider_names: list[str]) -> list[str]:
        preferred_order = ["anthropic", "openai", "gemini", "perplexity"]
        preferred = [provider for provider in preferred_order if provider in provider_names]
        if preferred:
            return preferred[:2]
        return provider_names[:2]

    def _preflight_available_providers(
        self,
        provider_names: list[str],
        content_type: str,
        language_hint: str,
    ) -> list[str]:
        # Return all configured providers as available without making billable API calls.
        # The old implementation sent a real analyze() request to each provider as a
        # "preflight probe" — this burned tokens, cost money, and could fail due to
        # JSON normalization issues rather than actual provider unavailability.
        # Actual availability is checked when the real analyze/rewrite call is made;
        # transient errors there are already handled by the retry and fallback logic.
        return sorted(provider_names)

    def _apply_safe_fallback_rewrite(
        self,
        text: str,
        changes: list[str],
        signals: list[str],
    ) -> str:
        rewritten = text
        lowered_changes = " ".join(changes).lower()
        lowered_signals = " ".join(signals).lower()

        # Strip templated markdown scaffolding when it is adding formality rather than meaning.
        if "structured" in lowered_changes or "whitepaper" in lowered_changes or "formal" in lowered_signals:
            rewritten = re.sub(r"(?m)^\s*---\s*$\n?", "", rewritten)
            rewritten = re.sub(r"(?m)^\s{0,3}##\s+", "", rewritten)
            rewritten = re.sub(r"(?m)^\s{0,3}#\s+\*\*(.*?)\*\*\s*$", r"\1", rewritten)
            rewritten = re.sub(r"(?m)^\s{0,3}\*(?:end|closing|conclusion)[^*\n]*\*\s*$", "", rewritten, flags=re.IGNORECASE)

        generic_replacements = {
            "Furthermore, ": "Also, ",
            "Moreover, ": "Also, ",
            "Additionally, ": "Also, ",
            "In addition, ": "Also, ",
            "However, ": "But ",
            "Therefore, ": "So ",
            "Indeed, ": "",
            "Notably, ": "",
            "Importantly, ": "",
            "In order to ": "To ",
            "utilize": "use",
            "numerous": "many",
            "individuals": "people",
        }
        for source, target in generic_replacements.items():
            rewritten = rewritten.replace(source, target)

        if "rhetoric" in lowered_changes or "persuasive" in lowered_signals or "parallel" in lowered_signals:
            rewritten = re.sub(
                r"\b([A-Z][^.;!?]{3,}?) is not ([^.;!?]{2,}?); it is ([^.;!?]{2,}?)\.",
                r"\1 isn't \2. It's \3.",
                rewritten,
            )
            rewritten = re.sub(
                r"\b([A-Z][^.;!?]{3,}?) is not ([^.;!?]{2,}?); it'?s ([^.;!?]{2,}?)\.",
                r"\1 isn't \2. It's \3.",
                rewritten,
            )

        if "generic rhetoric" in lowered_changes or "platitudes" in lowered_signals or "abstract" in lowered_signals:
            rewritten = rewritten.replace("It is", "It's")
            rewritten = rewritten.replace("That is", "That's")
            rewritten = rewritten.replace("There is", "There's")

        if "motivational" in lowered_changes or "repetitive" in lowered_signals:
            rewritten = re.sub(
                r"\b([A-Z][^.!?]{15,}?), and ([a-z][^.!?]{10,})\.",
                r"\1. \2.",
                rewritten,
            )
            rewritten = re.sub(
                r"\b([A-Z][^.!?]{15,}?) but ([a-z][^.!?]{10,})\.",
                r"\1. But \2.",
                rewritten,
            )

        rewritten = re.sub(r"\n{3,}", "\n\n", rewritten)
        rewritten = re.sub(r"[ \t]{2,}", " ", rewritten)
        return rewritten.strip()

    def _rewrite_has_provider_consensus(
        self,
        original_text: str,
        rewritten_text: str,
        review_provider_names: list[str],
        language_hint: str,
    ) -> bool:
        pending: list[str] = []
        for provider_name in review_provider_names:
            cache_key = (provider_name, original_text, rewritten_text)
            cached = self._rewrite_review_cache.get(cache_key)
            if cached is False:
                return False
            if cached is True:
                continue
            pending.append(provider_name)
        if not pending:
            return True

        with ThreadPoolExecutor(max_workers=min(len(pending), 4) or 1) as executor:
            futures = {
                executor.submit(
                    copy_context().run,
                    self.providers[provider_name].review_rewrite,
                    RewriteReviewRequest(
                        source_text=original_text,
                        rewritten_text=rewritten_text,
                        language_hint=language_hint,
                        model=self.providers[provider_name].default_model,
                        metadata={},
                    ),
                ): provider_name
                for provider_name in pending
            }
            for future in as_completed(futures):
                provider_name = futures[future]
                try:
                    review = future.result()
                except ProviderTransientError:
                    self._rewrite_review_cache[(provider_name, original_text, rewritten_text)] = False
                    return False
                except Exception:
                    self._rewrite_review_cache[(provider_name, original_text, rewritten_text)] = False
                    return False
                if not review.supported:
                    self._rewrite_review_cache[(provider_name, original_text, rewritten_text)] = False
                    return False
                self._rewrite_review_cache[(provider_name, original_text, rewritten_text)] = True
        return True

    def _record_candidate(
        self,
        candidates: list[dict[str, object]],
        stage: str,
        text: str,
        rejection_reason: str | None = None,
    ) -> None:
        if not self._debug_enabled():
            return
        candidates.append(
            {
                "stage": stage,
                "text": text[:2000],
                "rejection_reason": rejection_reason,
            }
        )

    def _debug_enabled(self) -> bool:
        return self.settings.log_level.upper() == "DEBUG"


def _contains_citation_markers(text: str) -> bool:
    return bool(re.search(r"\[\d+\]|\([A-Z][A-Za-z]+,\s*\d{4}\)", text))


def _strip_citation_markers(text: str) -> str:
    stripped = re.sub(r"\[\d+(?:\]\[\d+)*\]", "", text)
    stripped = re.sub(r"\s{2,}", " ", stripped)
    return stripped


def _contains_urls(text: str) -> bool:
    return "http://" in text or "https://" in text or "www." in text


def _strip_urls(text: str) -> str:
    stripped = re.sub(r"https?://\S+|www\.\S+", "", text)
    stripped = re.sub(r"\s{2,}", " ", stripped)
    return stripped


def _contains_reference_heading(text: str) -> bool:
    return bool(re.search(r"(?im)^\s{0,3}(references|bibliography|sources)\s*:?\s*$", text))


def _strip_reference_sections(text: str) -> str:
    pattern = re.compile(
        r"(?ims)\n\s{0,3}(references|bibliography|sources)\s*:?\s*\n.*$"
    )
    return re.sub(pattern, "", text).rstrip()


def _split_markdown_blocks(text: str) -> list[str]:
    return re.findall(r".*?(?:\n\s*\n|$)", text, flags=re.DOTALL)


def _starts_new_natural_section(block: str) -> bool:
    stripped = block.lstrip()
    if not stripped:
        return False
    return stripped.startswith("#") or stripped.startswith("##") or stripped.startswith("###")


def _first_meaningful_paragraph(text: str) -> str:
    for block in _split_markdown_blocks(text):
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("```"):
            continue
        return " ".join(stripped.split())[:280]
    return ""


def _detect_novel_facts(original: str, rewritten: str) -> list[str]:
    """Detect numbers, dates, percentages, and dollar amounts in the rewrite
    that are not present in the original text. Returns a list of novel elements.

    This is a deterministic check that does not rely on LLM judgment.
    """
    # Extract factual tokens from both texts
    original_facts = _extract_factual_tokens(original)
    rewritten_facts = _extract_factual_tokens(rewritten)

    # Novel facts = in rewrite but not in original
    novel = rewritten_facts - original_facts
    return sorted(novel)


def _extract_factual_tokens(text: str) -> set[str]:
    """Extract numbers, dates, percentages, dollar amounts, and standard
    references from text. Returns a set of normalized tokens."""
    tokens: set[str] = set()

    # Numbers (integers and decimals, excluding very common ones like 1, 2, 3)
    for match in re.finditer(r'\b(\d+\.?\d*)\b', text):
        num = match.group(1)
        # Skip single digits and very common numbers
        if len(num) >= 2 or float(num) >= 10:
            tokens.add(num)

    # Percentages
    for match in re.finditer(r'(\d+\.?\d*)\s*%', text):
        tokens.add(f"{match.group(1)}%")

    # Dollar amounts
    for match in re.finditer(r'\$\s*(\d[\d,]*\.?\d*)', text):
        tokens.add(f"${match.group(1)}")

    # Years (4-digit numbers between 1900-2099)
    for match in re.finditer(r'\b((?:19|20)\d{2})\b', text):
        tokens.add(match.group(1))

    # Standard/regulation references (e.g., "CFR 650", "NFPA 70B", "TIA-222-H")
    for match in re.finditer(r'\b([A-Z]{2,}[\s-]?\d+[A-Z]?(?:\.\d+)*)\b', text):
        tokens.add(match.group(1).strip())

    return tokens
