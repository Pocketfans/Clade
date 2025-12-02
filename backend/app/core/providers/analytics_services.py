"""
分析服务提供者 - 报告和分析服务

提供对分析服务的缓存访问：
- report_builder: 回合报告生成
- export_service: 数据导出
- focus_processor: 焦点批量处理
- critical_analyzer: 危机物种分析
- embedding_integration: 嵌入集成服务
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..config import Settings
    from ...services.analytics.report_builder import ReportBuilder
    from ...services.analytics.exporter import ExportService
    from ...services.analytics.focus_processor import FocusBatchProcessor
    from ...services.analytics.critical_analyzer import CriticalAnalyzer
    from ...services.analytics.embedding_integration import EmbeddingIntegrationService
    from ...ai.model_router import ModelRouter
    from ...services.system.embedding import EmbeddingService


class AnalyticsServiceProvider:
    """Mixin providing analytics and reporting services"""
    
    settings: 'Settings'
    _overrides: dict[str, Any]
    model_router: 'ModelRouter'
    embedding_service: 'EmbeddingService'
    
    def _get_or_override(self, name: str, factory: Callable[[], Any]) -> Any:
        """Get service instance, preferring override if set"""
        if name in self._overrides:
            return self._overrides[name]
        return factory()
    
    @cached_property
    def report_builder(self) -> 'ReportBuilder':
        use_v2 = getattr(self.settings, 'use_report_v2', True)
        if use_v2:
            from ...services.analytics.report_builder_v2 import ReportBuilderV2
            return self._get_or_override(
                'report_builder',
                lambda: ReportBuilderV2(self.model_router, batch_size=self.settings.focus_batch_size)
            )
        else:
            from ...services.analytics.report_builder import ReportBuilder
            return self._get_or_override(
                'report_builder',
                lambda: ReportBuilder(self.model_router)
            )
    
    @cached_property
    def export_service(self) -> 'ExportService':
        from ...services.analytics.exporter import ExportService
        return self._get_or_override(
            'export_service',
            lambda: ExportService(self.settings.reports_dir, self.settings.exports_dir)
        )
    
    @cached_property
    def focus_processor(self) -> 'FocusBatchProcessor':
        from ...services.analytics.focus_processor import FocusBatchProcessor
        return self._get_or_override(
            'focus_processor',
            lambda: FocusBatchProcessor(self.model_router, self.settings.focus_batch_size)
        )
    
    @cached_property
    def critical_analyzer(self) -> 'CriticalAnalyzer':
        from ...services.analytics.critical_analyzer import CriticalAnalyzer
        return self._get_or_override(
            'critical_analyzer',
            lambda: CriticalAnalyzer(self.model_router)
        )
    
    @cached_property
    def embedding_integration(self) -> 'EmbeddingIntegrationService':
        from ...services.analytics.embedding_integration import EmbeddingIntegrationService
        return self._get_or_override(
            'embedding_integration',
            lambda: EmbeddingIntegrationService(self.embedding_service, self.model_router)
        )

