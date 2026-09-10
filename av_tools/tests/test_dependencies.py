# Copyright (c) 2026, Aakvatech and Contributors
# See license.txt

import tomllib
from pathlib import Path
from unittest import TestCase

from packaging.requirements import Requirement
from packaging.version import Version


class TestDependencies(TestCase):
	@classmethod
	def setUpClass(cls):
		pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
		with pyproject_path.open("rb") as pyproject_file:
			project = tomllib.load(pyproject_file)["project"]

		cls.dependencies = {
			Requirement(dependency).name: Requirement(dependency)
			for dependency in project["dependencies"]
		}

	def test_openai_dependency_supports_raven_minimum(self):
		openai_requirement = self.dependencies["openai"]

		self.assertTrue(openai_requirement.specifier.contains(Version("2.30.0")))

	def test_openai_dependency_excludes_next_major_version(self):
		openai_requirement = self.dependencies["openai"]

		self.assertFalse(openai_requirement.specifier.contains(Version("3.0.0")))
