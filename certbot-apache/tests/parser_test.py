"""Tests for certbot_apache._internal.parser."""
import shutil
import unittest

try:
    import mock
except ImportError: # pragma: no cover
    from unittest import mock # type: ignore

from certbot import errors
from certbot.compat import os
import util


class BasicParserTest(util.ParserTest):
    """Apache Parser Test."""

    def setUp(self):  # pylint: disable=arguments-differ
        super().setUp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        shutil.rmtree(self.config_dir)
        shutil.rmtree(self.work_dir)

    def test_bad_parse(self):
        self.parser.parse_file(os.path.join(self.parser.root,
                                            "conf-available", "bad_conf_file.conf"))
        self.assertRaises(
            errors.PluginError, self.parser.check_parsing_errors, "httpd.aug")

    def test_bad_save(self):
        mock_save = mock.Mock()
        mock_save.side_effect = IOError
        self.parser.aug.save = mock_save
        self.assertRaises(errors.PluginError, self.parser.unsaved_files)

    def test_aug_version(self):
        mock_match = mock.Mock(return_value=["something"])
        self.parser.aug.match = mock_match
        # pylint: disable=protected-access
        self.assertEqual(self.parser.check_aug_version(),
                         ["something"])
        self.parser.aug.match.side_effect = RuntimeError
        self.assertFalse(self.parser.check_aug_version())

    def test_find_config_root_no_root(self):
        # pylint: disable=protected-access
        os.remove(self.parser.loc["root"])
        self.assertRaises(
            errors.NoInstallationError, self.parser._find_config_root)

    def test_parse_file(self):
        """Test parse_file.

        certbot.conf is chosen as the test file as it will not be
        included during the normal course of execution.

        """
        file_path = os.path.join(
            self.config_path, "not-parsed-by-default", "certbot.conf")

        self.parser.parse_file(file_path)  # pylint: disable=protected-access

        # search for the httpd incl
        matches = self.parser.aug.match(
            "/augeas/load/Httpd/incl [. ='%s']" % file_path)

        self.assertTrue(matches)

    def test_find_dir(self):
        test = self.parser.find_dir("Listen", "80")
        # This will only look in enabled hosts
        test2 = self.parser.find_dir("documentroot")

        self.assertEqual(len(test), 1)
        self.assertEqual(len(test2), 8)

    def test_add_dir(self):
        aug_default = "/files" + self.parser.loc["default"]
        self.parser.add_dir(aug_default, "AddDirective", "test")

        self.assertTrue(
            self.parser.find_dir("AddDirective", "test", aug_default))

        self.parser.add_dir(aug_default, "AddList", ["1", "2", "3", "4"])
        matches = self.parser.find_dir("AddList", None, aug_default)
        for i, match in enumerate(matches):
            self.assertEqual(self.parser.aug.get(match), str(i + 1))

    def test_add_dir_beginning(self):
        aug_default = "/files" + self.parser.loc["default"]
        self.parser.add_dir_beginning(aug_default,
                                      "AddDirectiveBeginning",
                                      "testBegin")

        self.assertTrue(
            self.parser.find_dir("AddDirectiveBeginning", "testBegin", aug_default))

        self.assertEqual(
            self.parser.aug.get(aug_default+"/directive[1]"),
                                "AddDirectiveBeginning")
        self.parser.add_dir_beginning(aug_default, "AddList", ["1", "2", "3", "4"])
        matches = self.parser.find_dir("AddList", None, aug_default)
        for i, match in enumerate(matches):
            self.assertEqual(self.parser.aug.get(match), str(i + 1))

    def test_empty_arg(self):
        self.assertEqual(None,
                          self.parser.get_arg("/files/whatever/nonexistent"))

    def test_add_dir_to_ifmodssl(self):
        """test add_dir_to_ifmodssl.

        Path must be valid before attempting to add to augeas

        """
        from certbot_apache._internal.parser import get_aug_path
        # This makes sure that find_dir will work
        self.parser.modules["mod_ssl.c"] = "/fake/path"

        self.parser.add_dir_to_ifmodssl(
            get_aug_path(self.parser.loc["default"]),
            "FakeDirective", ["123"])

        matches = self.parser.find_dir("FakeDirective", "123")

        self.assertEqual(len(matches), 1)
        self.assertTrue("IfModule" in matches[0])

    def test_add_dir_to_ifmodssl_multiple(self):
        from certbot_apache._internal.parser import get_aug_path
        # This makes sure that find_dir will work
        self.parser.modules["mod_ssl.c"] = "/fake/path"

        self.parser.add_dir_to_ifmodssl(
            get_aug_path(self.parser.loc["default"]),
            "FakeDirective", ["123", "456", "789"])

        matches = self.parser.find_dir("FakeDirective")

        self.assertEqual(len(matches), 3)
        self.assertTrue("IfModule" in matches[0])

    def test_get_aug_path(self):
        from certbot_apache._internal.parser import get_aug_path
        self.assertEqual("/files/etc/apache", get_aug_path("/etc/apache"))

    def test_set_locations(self):
        with mock.patch("certbot_apache._internal.parser.os.path") as mock_path:

            mock_path.isfile.side_effect = [False, False]

            # pylint: disable=protected-access
            results = self.parser._set_locations()

            self.assertEqual(results["default"], results["listen"])
            self.assertEqual(results["default"], results["name"])

    @mock.patch("certbot_apache._internal.parser.ApacheParser.find_dir")
    @mock.patch("certbot_apache._internal.parser.ApacheParser.get_arg")
    def test_parse_modules_bad_syntax(self, mock_arg, mock_find):
        mock_find.return_value = ["1", "2", "3", "4", "5", "6", "7", "8"]
        mock_arg.return_value = None
        with mock.patch("certbot_apache._internal.parser.logger") as mock_logger:
            self.parser.parse_modules()
            # Make sure that we got None return value and logged the file
            self.assertTrue(mock_logger.debug.called)

    @mock.patch("certbot_apache._internal.parser.ApacheParser.find_dir")
    @mock.patch("certbot_apache._internal.apache_util._get_runtime_cfg")
    def test_update_runtime_variables(self, mock_cfg, _):
        define_val = (
            'ServerRoot: "/etc/apache2"\n'
            'Main DocumentRoot: "/var/www"\n'
            'Main ErrorLog: "/var/log/apache2/error.log"\n'
            'Mutex ssl-stapling: using_defaults\n'
            'Mutex ssl-cache: using_defaults\n'
            'Mutex default: dir="/var/lock/apache2" mechanism=fcntl\n'
            'Mutex watchdog-callback: using_defaults\n'
            'PidFile: "/var/run/apache2/apache2.pid"\n'
            'Define: TEST\n'
            'Define: DUMP_RUN_CFG\n'
            'Define: U_MICH\n'
            'Define: TLS=443\n'
            'Define: example_path=Documents/path\n'
            'User: name="www-data" id=33 not_used\n'
            'Group: name="www-data" id=33 not_used\n'
        )
        inc_val = (
            'Included configuration files:\n'
            '  (*) /etc/apache2/apache2.conf\n'
            '    (146) /etc/apache2/mods-enabled/access_compat.load\n'
            '    (146) /etc/apache2/mods-enabled/alias.load\n'
            '    (146) /etc/apache2/mods-enabled/auth_basic.load\n'
            '    (146) /etc/apache2/mods-enabled/authn_core.load\n'
            '    (146) /etc/apache2/mods-enabled/authn_file.load\n'
            '    (146) /etc/apache2/mods-enabled/authz_core.load\n'
            '    (146) /etc/apache2/mods-enabled/authz_host.load\n'
            '    (146) /etc/apache2/mods-enabled/authz_user.load\n'
            '    (146) /etc/apache2/mods-enabled/autoindex.load\n'
            '    (146) /etc/apache2/mods-enabled/deflate.load\n'
            '    (146) /etc/apache2/mods-enabled/dir.load\n'
            '    (146) /etc/apache2/mods-enabled/env.load\n'
            '    (146) /etc/apache2/mods-enabled/filter.load\n'
            '    (146) /etc/apache2/mods-enabled/mime.load\n'
            '    (146) /etc/apache2/mods-enabled/mpm_event.load\n'
            '    (146) /etc/apache2/mods-enabled/negotiation.load\n'
            '    (146) /etc/apache2/mods-enabled/reqtimeout.load\n'
            '    (146) /etc/apache2/mods-enabled/setenvif.load\n'
            '    (146) /etc/apache2/mods-enabled/socache_shmcb.load\n'
            '    (146) /etc/apache2/mods-enabled/ssl.load\n'
            '    (146) /etc/apache2/mods-enabled/status.load\n'
            '    (147) /etc/apache2/mods-enabled/alias.conf\n'
            '    (147) /etc/apache2/mods-enabled/autoindex.conf\n'
            '    (147) /etc/apache2/mods-enabled/deflate.conf\n'
        )
        mod_val = (
            'Loaded Modules:\n'
            ' core_module (static)\n'
            ' so_module (static)\n'
            ' watchdog_module (static)\n'
            ' http_module (static)\n'
            ' log_config_module (static)\n'
            ' logio_module (static)\n'
            ' version_module (static)\n'
            ' unixd_module (static)\n'
            ' access_compat_module (shared)\n'
            ' alias_module (shared)\n'
            ' auth_basic_module (shared)\n'
            ' authn_core_module (shared)\n'
            ' authn_file_module (shared)\n'
            ' authz_core_module (shared)\n'
            ' authz_host_module (shared)\n'
            ' authz_user_module (shared)\n'
            ' autoindex_module (shared)\n'
            ' deflate_module (shared)\n'
            ' dir_module (shared)\n'
            ' env_module (shared)\n'
            ' filter_module (shared)\n'
            ' mime_module (shared)\n'
            ' mpm_event_module (shared)\n'
            ' negotiation_module (shared)\n'
            ' reqtimeout_module (shared)\n'
            ' setenvif_module (shared)\n'
            ' socache_shmcb_module (shared)\n'
            ' ssl_module (shared)\n'
            ' status_module (shared)\n'
        )

        def mock_get_vars(cmd):
            """Mock command output"""
            if cmd[-1] == "DUMP_RUN_CFG":
                return define_val
            elif cmd[-1] == "DUMP_INCLUDES":
                return inc_val
            elif cmd[-1] == "DUMP_MODULES":
                return mod_val
            return None  # pragma: no cover

        mock_cfg.side_effect = mock_get_vars

        expected_vars = {"TEST": "", "U_MICH": "", "TLS": "443",
                         "example_path": "Documents/path"}

        self.parser.modules = {}
        with mock.patch(
            "certbot_apache._internal.parser.ApacheParser.parse_file") as mock_parse:
            self.parser.update_runtime_variables()
            self.assertEqual(self.parser.variables, expected_vars)
            self.assertEqual(len(self.parser.modules), 58)
            # None of the includes in inc_val should be in parsed paths.
            # Make sure we tried to include them all.
            self.assertEqual(mock_parse.call_count, 25)

    @mock.patch("certbot_apache._internal.parser.ApacheParser.find_dir")
    @mock.patch("certbot_apache._internal.apache_util._get_runtime_cfg")
    def test_update_runtime_variables_alt_values(self, mock_cfg, _):
        inc_val = (
            'Included configuration files:\n'
            '  (*) {0}\n'
            '    (146) /etc/apache2/mods-enabled/access_compat.load\n'
            '    (146) {1}/mods-enabled/alias.load\n'
        ).format(self.parser.loc["root"],
                 os.path.dirname(self.parser.loc["root"]))

        mock_cfg.return_value = inc_val
        self.parser.modules = {}

        with mock.patch(
            "certbot_apache._internal.parser.ApacheParser.parse_file") as mock_parse:
            self.parser.update_runtime_variables()
            # No matching modules should have been found
            self.assertEqual(len(self.parser.modules), 0)
            # Only one of the three includes do not exist in already parsed
            # path derived from root configuration Include statements
            self.assertEqual(mock_parse.call_count, 1)

    @mock.patch("certbot_apache._internal.apache_util._get_runtime_cfg")
    def test_update_runtime_vars_bad_output(self, mock_cfg):
        mock_cfg.return_value = "Define: TLS=443=24"
        self.parser.update_runtime_variables()

        mock_cfg.return_value = "Define: DUMP_RUN_CFG\nDefine: TLS=443=24"
        self.assertRaises(
            errors.PluginError, self.parser.update_runtime_variables)

    @mock.patch("certbot_apache._internal.apache_util.subprocess.Popen")
    def test_update_runtime_vars_bad_ctl(self, mock_popen):
        mock_popen.side_effect = OSError
        self.assertRaises(
            errors.MisconfigurationError,
            self.parser.update_runtime_variables)

    @mock.patch("certbot_apache._internal.apache_util.subprocess.Popen")
    def test_update_runtime_vars_bad_exit(self, mock_popen):
        mock_popen().communicate.return_value = ("", "")
        mock_popen.returncode = -1
        self.assertRaises(
            errors.MisconfigurationError,
            self.parser.update_runtime_variables)

    def test_add_comment(self):
        from certbot_apache._internal.parser import get_aug_path
        self.parser.add_comment(get_aug_path(self.parser.loc["name"]), "123456")
        comm = self.parser.find_comments("123456")
        self.assertEqual(len(comm), 1)
        self.assertTrue(self.parser.loc["name"] in comm[0])


class ParserInitTest(util.ApacheTest):
    def setUp(self):  # pylint: disable=arguments-differ
        super().setUp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        shutil.rmtree(self.config_dir)
        shutil.rmtree(self.work_dir)

    @mock.patch("certbot_apache._internal.parser.init_augeas")
    def test_prepare_no_augeas(self, mock_init_augeas):
        from certbot_apache._internal.parser import ApacheParser
        mock_init_augeas.side_effect = errors.NoInstallationError
        self.config.config_test = mock.Mock()
        self.assertRaises(
            errors.NoInstallationError, ApacheParser,
            os.path.relpath(self.config_path), "/dummy/vhostpath",
            version=(2, 4, 22), configurator=self.config)

    def test_init_old_aug(self):
        from certbot_apache._internal.parser import ApacheParser
        with mock.patch("certbot_apache._internal.parser.ApacheParser.check_aug_version") as mock_c:
            mock_c.return_value = False
            self.assertRaises(
                errors.NotSupportedError,
                ApacheParser, os.path.relpath(self.config_path),
                "/dummy/vhostpath", version=(2, 4, 22), configurator=self.config)

    @mock.patch("certbot_apache._internal.apache_util._get_runtime_cfg")
    def test_unparseable(self, mock_cfg):
        from certbot_apache._internal.parser import ApacheParser
        mock_cfg.return_value = ('Define: TEST')
        self.assertRaises(
            errors.PluginError,
            ApacheParser, os.path.relpath(self.config_path),
            "/dummy/vhostpath", version=(2, 2, 22), configurator=self.config)

    def test_root_normalized(self):
        from certbot_apache._internal.parser import ApacheParser

        with mock.patch("certbot_apache._internal.parser.ApacheParser."
                        "update_runtime_variables"):
            path = os.path.join(
                self.temp_dir,
                "debian_apache_2_4/////multiple_vhosts/../multiple_vhosts/apache2")

            parser = ApacheParser(path, "/dummy/vhostpath", configurator=self.config)

        self.assertEqual(parser.root, self.config_path)

    def test_root_absolute(self):
        from certbot_apache._internal.parser import ApacheParser
        with mock.patch("certbot_apache._internal.parser.ApacheParser."
                        "update_runtime_variables"):
            parser = ApacheParser(
                os.path.relpath(self.config_path),
                "/dummy/vhostpath", configurator=self.config)

        self.assertEqual(parser.root, self.config_path)

    def test_root_no_trailing_slash(self):
        from certbot_apache._internal.parser import ApacheParser
        with mock.patch("certbot_apache._internal.parser.ApacheParser."
                        "update_runtime_variables"):
            parser = ApacheParser(
                self.config_path + os.path.sep,
                "/dummy/vhostpath", configurator=self.config)
        self.assertEqual(parser.root, self.config_path)


if __name__ == "__main__":
    unittest.main()  # pragma: no cover
