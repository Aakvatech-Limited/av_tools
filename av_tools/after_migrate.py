from av_tools.patches.v1_0.migrate_ai_integration_site_data import (
	execute as migrate_ai_integration_site_data,
)
from av_tools.patches.v1_0.migrate_report_extension_site_data import (
	execute as migrate_report_extension_site_data,
)
from av_tools.weigh_bridge.custom_fields import setup_custom_fields


def run_after_migrate():
	setup_custom_fields()
	migrate_ai_integration_site_data()
	migrate_report_extension_site_data()
