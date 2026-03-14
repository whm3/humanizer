from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from humanizer.input_loading import detect_content_type, resolve_text_input
from humanizer.providers.base import (
    ProviderAdapter,
    ProviderRequest,
    RewriteRequest,
    RewriteReviewRequest,
)


logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self, settings: Settings, providers: dict[str, ProviderAdapter]):
        self.settings = settings
        self.providers = providers
        self._rewrite_review_cache: dict[tuple[str, str, str], bool] = {}

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
                    self._analyze_with_provider,
                    provider_name=provider_name,
                    request=request,
                    input_text=input_text,
                    content_type=content_type,
                    profile_name=profile.name,
                    system_prompt=profile.system_prompt,
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
                        analysis=analysis,
                    )
                )
                break

            rewritten_text = self._rewrite_text(
                current_text,
                analysis.summary.humanization_changes,
                analysis.consensus.signals,
                analysis.selected_providers,
                humanizer_provider,
                humanizer_model,
                request.language_hint,
                iteration_index,
                analysis.consensus.score,
                request.threshold,
                request.fast_mode,
            )
            iterations.append(
                HumanizeIteration(
                    iteration=iteration_index,
                    input_text=current_text,
                    output_text=rewritten_text,
                    applied_changes=analysis.summary.humanization_changes,
                    analysis=analysis,
                )
            )
            current_text = rewritten_text
            logger.debug(
                "humanize.iteration iteration=%d prior_score=%.4f rewritten_changed=%s",
                iteration_index,
                analysis.consensus.score,
                rewritten_text.strip() != iterations[-1].input_text.strip(),
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
        statuses: list[dict[str, str | bool]] = []
        for provider_name in sorted(self.providers):
            provider = self.providers[provider_name]
            available = True
            detail = "available"
            try:
                provider.analyze(
                    ProviderRequest(
                        text="Preflight availability probe.",
                        profile_name="ai_detection",
                        language_hint="en",
                        content_type="text",
                        system_prompt="Classify the text for likely AI assistance and return normalized scoring signals.",
                        model=provider.default_model,
                        metadata={"preflight": True},
                    )
                )
            except Exception as exc:
                available = False
                detail = str(exc)
                logger.warning("provider.preflight_unavailable provider=%s detail=%s", provider_name, detail)
            statuses.append(
                {
                    "name": provider_name,
                    "available": available,
                    "default_model": provider.default_model,
                    "detail": detail,
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
        likely_ai_votes = sum(1 for label in labels if "ai" in label)
        label = labels[0] if len(set(labels)) == 1 else (
            "likely_ai_assisted" if likely_ai_votes >= (len(labels) / 2) else "likely_human"
        )
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
    ) -> str:
        segments = text.split("```")
        rewritten_segments: list[str] = []
        rewrite_review_providers = self._select_rewrite_review_providers(
            review_provider_names,
            humanizer_provider,
            fast_mode,
        )
        for index, segment in enumerate(segments):
            if index % 2 == 1:
                rewritten_segments.append(f"```{segment}```")
                continue
            rewritten_segments.append(
                self._rewrite_prose_segment(
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
                )
            )
        return "".join(rewritten_segments)

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
    ) -> str:
        if not text.strip():
            return text
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
                metadata={},
            )
        )
        if not rewritten.strip():
            rewritten = text
        guarded = self._apply_rewrite_guardrails(text, rewritten, review_provider_names, language_hint)
        if (
            guarded.strip() == text.strip()
            and prior_score > (target_score + 0.20)
        ):
            fallback = self._apply_safe_fallback_rewrite(text, changes, signals)
            if fallback.strip() != text.strip():
                guarded = self._apply_rewrite_guardrails(
                    text,
                    fallback,
                    review_provider_names,
                    language_hint,
                )
        return guarded

    def _apply_rewrite_guardrails(
        self,
        original_text: str,
        rewritten_text: str,
        review_provider_names: list[str],
        language_hint: str,
    ) -> str:
        sanitized = rewritten_text

        if not _contains_citation_markers(original_text):
            sanitized = _strip_citation_markers(sanitized)
        if not _contains_urls(original_text):
            sanitized = _strip_urls(sanitized)
        if not _contains_reference_heading(original_text):
            sanitized = _strip_reference_sections(sanitized)

        if sanitized.strip() == original_text.strip():
            return original_text

        if not review_provider_names:
            return original_text

        if not self._rewrite_has_provider_consensus(
            original_text,
            sanitized,
            review_provider_names,
            language_hint,
        ):
            return original_text

        return sanitized.strip() or original_text

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
        available: list[str] = []
        with ThreadPoolExecutor(max_workers=min(len(provider_names), 5) or 1) as executor:
            futures = {
                executor.submit(
                    self.providers[provider_name].analyze,
                    ProviderRequest(
                        text="Preflight availability probe.",
                        profile_name="ai_detection",
                        language_hint=language_hint,
                        content_type=content_type,
                        system_prompt="Classify the text for likely AI assistance and return normalized scoring signals.",
                        model=self.providers[provider_name].default_model,
                        metadata={"preflight": True},
                    ),
                ): provider_name
                for provider_name in provider_names
            }
            for future in as_completed(futures):
                provider_name = futures[future]
                try:
                    future.result()
                    available.append(provider_name)
                except Exception as exc:
                    logger.warning("provider.preflight_unavailable provider=%s detail=%s", provider_name, exc)
        return sorted(available)

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
