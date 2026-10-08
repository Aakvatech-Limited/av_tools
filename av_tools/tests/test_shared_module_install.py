from unittest import TestCase
from unittest.mock import MagicMock, patch

from av_tools import install


class TestSharedModuleInstall(TestCase):
	def setUp(self):
		self.mock = MagicMock()
		self.mock.get_module_list.return_value = ["Av Tools", "AuthOTP", "Feedback", "Trade In"]
		self.mock.db.exists.return_value = False
		self.mock.db.get_value.return_value = None
		self.mock.throw.side_effect = RuntimeError("module conflict")
		patcher = patch.object(install, "frappe", self.mock)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_fresh_install_does_not_delete_or_commit(self):
		install.before_install()
		self.mock.db.delete.assert_not_called()
		self.mock.db.commit.assert_not_called()

	def test_legacy_shared_modules_are_reregistered_without_commit(self):
		self.mock.db.exists.side_effect = lambda doctype, name: name in install.SHARED_MODULES
		self.mock.db.get_value.return_value = "csf_tz"
		install.before_install()
		self.assertEqual(self.mock.db.delete.call_count, 3)
		for call in self.mock.db.delete.call_args_list:
			self.assertEqual(call.args[0], "Module Def")
		self.mock.db.commit.assert_not_called()

	def test_unknown_owner_blocks_before_any_delete(self):
		self.mock.db.exists.return_value = True
		self.mock.db.get_value.side_effect = ["av_tools", "csf_tz", "another_app"]
		with self.assertRaises(RuntimeError):
			install.before_install()
		self.mock.db.delete.assert_not_called()

	def test_nonshared_csf_module_is_not_claimed(self):
		self.mock.db.exists.return_value = True
		self.mock.db.get_value.return_value = "csf_tz"
		with self.assertRaises(RuntimeError):
			install.before_install()
		self.mock.db.delete.assert_not_called()

	def test_module_discovery_error_does_not_use_stale_fallback(self):
		self.mock.get_module_list.side_effect = RuntimeError("broken app")
		with self.assertRaises(RuntimeError):
			install.before_install()
		self.mock.db.delete.assert_not_called()

	def test_existing_otp_records_are_preserved_during_handover(self):
		self.mock.db.exists.return_value = True
		self.mock.db.get_value.side_effect = lambda doctype, name, field: (
			"CSF TZ" if doctype == "DocType" else "csf_tz"
		)
		install.reconcile_shared_modules()
		self.assertEqual(self.mock.db.set_value.call_count, 5)
		self.mock.db.set_value.assert_any_call(
			"DocType", "OTP Register", "module", "AuthOTP", update_modified=False
		)
		self.mock.db.delete.assert_not_called()
		self.mock.db.commit.assert_not_called()
		self.mock.clear_cache.assert_called_once_with(doctype="OTP Register")

	def test_reconciliation_is_noop_for_canonical_or_other_owners(self):
		self.mock.db.exists.return_value = True
		for owner in ("av_tools", "another_app"):
			self.mock.db.get_value.return_value = owner
			install.reconcile_shared_modules()
		self.mock.db.set_value.assert_not_called()
		self.mock.db.delete.assert_not_called()
