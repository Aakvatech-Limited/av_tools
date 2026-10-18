"""Add source fields only. Never create Assets or enable the feature in a migration."""

from av_tools.utils.create_custom_fields import create_fields_from_json, load_json


def execute():
	create_fields_from_json(load_json("no_time_appropriation_asset_fields.json"))
