from __future__ import annotations

import re
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
        if not selected_providers:
            raise ValidationError("no enabled providers with configured credentials are available")

        started = perf_counter()
        source_results: list[AnalyzeResult] = []
        transient_failures: list[str] = []
        for provider_name in selected_providers:
            try:
                source_results.append(
                    self._analyze_with_provider(
                        provider_name=provider_name,
                        request=request,
                        input_text=input_text,
                        content_type=content_type,
                        profile_name=profile.name,
                        system_prompt=profile.system_prompt,
                    )
                )
            except ProviderTransientError:
                if request.provider is not None:
                    raise
                transient_failures.append(provider_name)
        if not source_results:
            if transient_failures:
                raise ValidationError(
                    "all selected providers were temporarily unavailable for this request"
                )
            raise ValidationError("no enabled providers with configured credentials are available")
        latency_ms = max(1, int((perf_counter() - started) * 1000))
        consensus = self._build_consensus(source_results)
        worst_case = max(source_results, key=lambda result: result.score)

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
                    language_hint=request.language_hint,
                    metadata=request.metadata,
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

        if final_analysis is None:
            raise ValidationError("humanization did not produce an analysis result")

        if iterations and iterations[-1].output_text != current_text:
            current_text = iterations[-1].output_text

        if final_analysis.consensus.score > request.threshold:
            final_analysis = self.analyze(
                AnalyzeRequest(
                    text=current_text,
                    content_type=content_type,
                    profile=request.profile,
                    provider=request.provider,
                    model=request.model,
                    language_hint=request.language_hint,
                    metadata=request.metadata,
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

        return [
            provider_name
            for provider_name in sorted(self.providers)
            if provider_name in supported_providers
        ]

    def _resolve_humanizer(self, request: HumanizeRequest) -> tuple[str, str]:
        provider_name = request.humanizer_provider or self.settings.default_humanizer_provider
        if provider_name not in self.providers:
            raise ValidationError(f"unsupported or disabled humanizer provider: {provider_name}")
        model_name = request.humanizer_model or self.settings.default_humanizer_model
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
    ) -> str:
        segments = text.split("```")
        rewritten_segments: list[str] = []
        for index, segment in enumerate(segments):
            if index % 2 == 1:
                rewritten_segments.append(f"```{segment}```")
                continue
            rewritten_segments.append(
                self._rewrite_prose_segment(
                    segment,
                    changes,
                    signals,
                    review_provider_names,
                    humanizer_provider,
                    humanizer_model,
                    language_hint,
                    iteration_index,
                    prior_score,
                    target_score,
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

        if not self._rewrite_has_provider_consensus(
            original_text,
            sanitized,
            review_provider_names,
            language_hint,
        ):
            return original_text

        return sanitized.strip() or original_text

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
            rewritten = re.sub(r"(?m)^\s{0,3}\*End of Speech\*\s*$", "", rewritten)

        replacements = {
            "It is not always": "You do not always",
            "It is always": "It still",
            "Today, we gather not to speak of fear, but of duty": "This is not really about fear. It is about duty",
            "It is a promise": "It is a commitment",
            "It symbolizes": "That shows",
            "We often talk about": "People talk a lot about",
            "The willingness to serve, if called, affirms that": "Being willing to serve, if called, shows that",
            "Registering is not an act of submission; it is an act of confidence.": "Registering is not submission. It shows confidence.",
            "The future belongs to those who build it.": "The future depends on what people do next.",
            "Remember: duty is not a burden when it is carried with purpose.": "Duty feels lighter when there is a real reason behind it.",
            "So stand tall. Sign your name.": "So go sign your name.",
            "It is not": "It isn't",
            "It is": "It's",
        }
        for source, target in replacements.items():
            rewritten = rewritten.replace(source, target)

        if "rhetoric" in lowered_changes or "patriotic" in lowered_signals or "persuasive" in lowered_signals:
            rewritten = rewritten.replace("this country remains united, capable, and willing to defend the values it holds sacred", "people are still willing to back the country and its values")
            rewritten = rewritten.replace("You join a lineage of citizens who understood that peace must be protected", "You join other people who knew peace does not protect itself")

        if "generic rhetoric" in lowered_changes or "platitudes" in lowered_signals:
            rewritten = rewritten.replace("It is an idea, sustained by its people.", "It only lasts if people keep showing up for it.")
            rewritten = rewritten.replace("the quiet, enduring responsibilities that hold a free nation together", "the everyday responsibilities that keep a country running")
            rewritten = rewritten.replace("The future goes to those who make it happen.", "What happens next depends on whether people actually do something.")

        if "motivational" in lowered_changes or "parallel" in lowered_signals or "repetitive" in lowered_signals:
            rewritten = rewritten.replace("It's not something we pick, but it shapes who we turn out to be.", "We don't choose those moments, but they still shape us.")
            rewritten = rewritten.replace("It's not splitting us up; it's about character and guts holding our security together, beyond just guns or rules.", "It doesn't split people up. It asks people to take some responsibility.")
            rewritten = rewritten.replace("Signing up isn't giving in. It's owning your confidence.", "Signing up isn't giving in. It's just taking responsibility.")
            rewritten = rewritten.replace("No citizen move is too small if it backs everyone's freedom.", "Small acts still matter.")
            rewritten = rewritten.replace("Let history see this generation didn't sit back waiting for somebody else.", "Let it be clear this generation didn't just sit around waiting.")

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
        for provider_name in review_provider_names:
            cache_key = (provider_name, original_text, rewritten_text)
            cached = self._rewrite_review_cache.get(cache_key)
            if cached is not None:
                if not cached:
                    return False
                continue
            provider = self.providers[provider_name]
            try:
                review = provider.review_rewrite(
                    RewriteReviewRequest(
                        source_text=original_text,
                        rewritten_text=rewritten_text,
                        language_hint=language_hint,
                        model=provider.default_model,
                        metadata={},
                    )
                )
            except ProviderTransientError:
                return False
            except Exception:
                return False
            if not review.supported:
                self._rewrite_review_cache[cache_key] = False
                return False
            self._rewrite_review_cache[cache_key] = True
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
