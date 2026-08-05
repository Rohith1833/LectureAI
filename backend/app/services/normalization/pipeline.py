import time
from typing import List, Dict, Any, Tuple
from loguru import logger

from app.schemas.document import DocumentExtractionResult
from app.services.normalization.base import (
    BaseNormalizer,
    PipelineLifecycleHook,
    NormalizationContext,
    NormalizationReport,
    StageResult,
    StageMetrics,
)


class NormalizationPipeline:
    """Orchestrates ordered registration, lifecycles, fault-tolerant execution, and reporting of normalizers."""

    def __init__(self):
        self.steps: List[BaseNormalizer] = []
        self.hooks: List[PipelineLifecycleHook] = []

    @classmethod
    def create_default_pipeline(cls) -> "NormalizationPipeline":
        """Instantiate and configure the pipeline with default text normalizers in order."""
        pipeline = cls()
        from app.services.normalization.unicode_normalizer import UnicodeNormalizer
        from app.services.normalization.control_character_normalizer import ControlCharacterNormalizer
        from app.services.normalization.whitespace_normalizer import WhitespaceNormalizer
        from app.services.normalization.empty_block_normalizer import EmptyBlockNormalizer

        pipeline.register_step(UnicodeNormalizer())
        pipeline.register_step(ControlCharacterNormalizer())
        pipeline.register_step(WhitespaceNormalizer())
        pipeline.register_step(EmptyBlockNormalizer())
        return pipeline

    def register_step(self, step: BaseNormalizer) -> None:
        """Add a normalization stage to the execution pipeline sequence."""
        self.steps.append(step)
        logger.info("Registered normalization step: {}", step.get_name())

    def register_hook(self, hook: PipelineLifecycleHook) -> None:
        """Register a pipeline lifecycle hooks observer listener."""
        self.hooks.append(hook)

    def execute(
        self, doc: DocumentExtractionResult, context: NormalizationContext
    ) -> Tuple[DocumentExtractionResult, NormalizationReport]:
        """Execute all registered and enabled normalizers over the canonical document in order."""
        logger.info(
            "Starting document normalization pipeline for upload: {}",
            context.metadata.upload_id,
        )

        pipeline_start = time.perf_counter()
        current_doc = doc

        # Fire before_pipeline hooks
        for hook in self.hooks:
            try:
                hook.before_pipeline(self, current_doc, context)
            except Exception as hook_err:
                logger.error("Error executing before_pipeline hook: {}", str(hook_err))

        steps_executed: List[str] = []
        stage_metrics_map: Dict[str, StageMetrics] = {}

        for step in self.steps:
            step_name = step.get_name()

            # Check if this step is disabled in metadata configuration
            enabled_configs = context.metadata.config.get("normalization_steps", {})
            # If explicit setting is False, skip this step
            if enabled_configs.get(step_name, True) is False:
                logger.info("Normalization step {} is disabled in config; skipping.", step_name)
                continue

            steps_executed.append(step_name)

            # Fire before_stage hooks
            for hook in self.hooks:
                try:
                    hook.before_stage(self, step_name, current_doc, context)
                except Exception as hook_err:
                    logger.error("Error executing before_stage hook: {}", str(hook_err))

            stage_start = time.perf_counter()
            
            try:
                # Execute normalizer stage
                stage_result = step.run(current_doc, context)
                
                # Calculate elapsed time in milliseconds
                elapsed_ms = round((time.perf_counter() - stage_start) * 1000.0, 3)
                stage_result.metrics.execution_time_ms = elapsed_ms

                # Record results
                current_doc = stage_result.document
                context.add_transformations(stage_result.transformations)
                stage_metrics_map[step_name] = stage_result.metrics

                # Take logical document snapshot version
                context.take_snapshot(step_name, current_doc)

                # Fire after_stage hooks
                for hook in self.hooks:
                    try:
                        hook.after_stage(self, step_name, current_doc, context, stage_result)
                    except Exception as hook_err:
                        logger.error("Error executing after_stage hook: {}", str(hook_err))

            except Exception as step_err:
                # Fault tolerance: catch normalizer failures, log, register stats, and proceed
                elapsed_ms = round((time.perf_counter() - stage_start) * 1000.0, 3)
                logger.error(
                    "Normalization step {} failed with exception: {}. Continuing pipeline execution.",
                    step_name,
                    str(step_err),
                )
                
                # Create fail result metrics
                fail_metrics = StageMetrics(
                    execution_time_ms=elapsed_ms,
                    errors=[str(step_err)],
                    warnings=["Normalizer failed during run execution"],
                )
                stage_metrics_map[step_name] = fail_metrics

                # Take unchanged document snapshot version
                context.take_snapshot(f"{step_name}_FAILED", current_doc)

                # Fire after_stage hook with dummy result
                dummy_result = StageResult(
                    document=current_doc,
                    transformations=[],
                    metrics=fail_metrics,
                )
                for hook in self.hooks:
                    try:
                        hook.after_stage(self, step_name, current_doc, context, dummy_result)
                    except Exception as hook_err:
                        logger.error("Error executing after_stage hook: {}", str(hook_err))

        # Pipeline complete. Build report
        total_time_ms = round((time.perf_counter() - pipeline_start) * 1000.0, 3)
        transformations = context.get_transformations()

        report = NormalizationReport(
            steps_executed=steps_executed,
            total_transformations=len(transformations),
            total_execution_time_ms=total_time_ms,
            stage_metrics=stage_metrics_map,
            transformations=transformations,
        )

        # Fire pipeline_complete hooks
        for hook in self.hooks:
            try:
                hook.pipeline_complete(self, current_doc, context, report)
            except Exception as hook_err:
                logger.error("Error executing pipeline_complete hook: {}", str(hook_err))

        logger.info(
            "Document normalization pipeline completed in {} ms. Total transformations: {}",
            total_time_ms,
            len(transformations),
        )

        return current_doc, report
