"""Static and mocked checks for the cedar-demo workshop change.

Run from the repository root (no root, systemd, or cedarling needed):

    python3 -m unittest discover -s tests -v

Integration checks that need Ubuntu 24.04, systemd and root live in
tools/test-demo-service.sh and are NOT exercised here.
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "operations.json").read_text())

# Maintained documentation and help text (idea.md is a historical brainstorm).
DOC_FILES = [
    ROOT / "README.md",
    ROOT / "workshop-overview.md",
    ROOT / "docs" / "cedudo.md",
    ROOT / "docs" / "demo-service.md",
    ROOT / "cedudo.py",
    ROOT / "tools" / "cedudo-simulate.py",
    ROOT / ".kiro" / "specs" / "cedar-sudo-workshop" / "requirements.md",
    ROOT / ".kiro" / "specs" / "cedar-sudo-workshop" / "design.md",
]


def load_source(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_cedudo():
    """Import cedudo.py with a stub cedarling_python."""
    stub = types.ModuleType("cedarling_python")
    for name in (
        "BootstrapConfig", "CedarEntityMapping", "Cedarling",
        "EntityData", "RequestUnsigned",
    ):
        setattr(stub, name, mock.MagicMock())
    with mock.patch.dict(sys.modules, {"cedarling_python": stub}):
        return load_source("cedudo_under_test", ROOT / "cedudo.py")


class ManifestTests(unittest.TestCase):
    def test_operation_ids(self):
        self.assertEqual(
            set(MANIFEST), {"read-logs", "restart-demo", "restart-ssh"}
        )
        self.assertNotIn("root-shell", MANIFEST)

    def test_read_logs_exact_argv(self):
        self.assertEqual(MANIFEST["read-logs"]["argv"], [
            "/usr/bin/journalctl", "--unit=cedar-demo.service",
            "--lines=20", "--no-pager", "--output=short-iso",
        ])

    def test_restart_demo_exact_argv(self):
        self.assertEqual(MANIFEST["restart-demo"]["argv"], [
            "/usr/bin/systemctl", "--no-ask-password", "--no-pager",
            "restart", "cedar-demo.service",
        ])

    def test_cedar_mapping_preserved(self):
        expect = {
            "read-logs": ("read-logs", "cedar-demo", False),
            "restart-demo": ("restart", "cedar-demo", False),
            "restart-ssh": ("restart", "ssh", True),
        }
        for op_id, (action, resource, critical) in expect.items():
            op = MANIFEST[op_id]
            self.assertEqual(op["action_type"], "Linux::Action")
            self.assertEqual(op["action_id"], action, op_id)
            self.assertEqual(op["resource_type"], "Linux::Service")
            self.assertEqual(op["resource_id"], resource, op_id)
            self.assertIs(op["resource_attributes"]["critical"], critical)

    def test_ssh_stays_simulated(self):
        argv = MANIFEST["restart-ssh"]["argv"]
        self.assertEqual(argv[0], "/usr/bin/echo")
        self.assertIn("SIMULATED", argv[1])
        for op in MANIFEST.values():
            if op is not MANIFEST["restart-ssh"]:
                self.assertNotIn("ssh", " ".join(op["argv"]))

    def test_real_ops_fixed_absolute_no_shell(self):
        for op_id in ("read-logs", "restart-demo"):
            argv = MANIFEST[op_id]["argv"]
            self.assertTrue(os.path.isabs(argv[0]))
            self.assertNotIn(argv[0].rsplit("/", 1)[1], {"sh", "bash"})
            self.assertNotIn("-f", argv)
            self.assertNotIn("--follow", argv)
        self.assertIn("--no-pager", MANIFEST["read-logs"]["argv"])
        self.assertIn("--lines=20", MANIFEST["read-logs"]["argv"])

    def test_only_cedar_demo_is_targeted(self):
        for op_id in ("read-logs", "restart-demo"):
            units = [a for a in MANIFEST[op_id]["argv"] if "service" in a]
            self.assertTrue(units and all("cedar-demo.service" in u for u in units))


class DocumentationTests(unittest.TestCase):
    def test_no_stale_restart_command(self):
        stale = re.compile(r"cedudo restart(?![-\w])")
        for path in DOC_FILES:
            for n, line in enumerate(path.read_text().splitlines(), 1):
                self.assertIsNone(stale.search(line), f"{path.name}:{n}: {line}")

    def test_no_stale_operation_names(self):
        for path in DOC_FILES:
            text = path.read_text()
            for old in ("view-logs", "status-demo"):
                self.assertNotIn(old, text, f"{path.name} mentions {old}")

    def test_docs_and_help_cover_every_operation(self):
        cedudo = load_cedudo()
        for op_id in MANIFEST:
            self.assertIn(op_id, cedudo.MANUAL)
            for path in (ROOT / "README.md", ROOT / "docs" / "cedudo.md",
                         ROOT / "workshop-overview.md"):
                self.assertIn(f"`{op_id}`", path.read_text(), path.name)

    def test_help_marks_ssh_simulated_and_others_real(self):
        manual = load_cedudo().MANUAL
        self.assertRegex(manual, r"restart-ssh[\s\S]{0,120}SIMULATED")
        self.assertRegex(manual, r"restart-demo[\s\S]{0,120}REAL")

    def test_cedudo_commands_in_code_blocks_are_known(self):
        known = set(MANIFEST) | {"root-shell"}
        pat = re.compile(r"^\s*(?:[$#]\s*)?(?:sudo )?cedudo (explain )?([a-z][a-z0-9-]*)")
        for path in DOC_FILES:
            in_code = False
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if line.lstrip().startswith("```"):
                    in_code = not in_code
                elif in_code:
                    m = pat.match(line)
                    if m and (m.group(1) or m.group(2) != "explain"):
                        self.assertIn(m.group(2), known, f"{path.name}:{n}: {line}")

    def test_exercise_covers_required_steps(self):
        text = (ROOT / "workshop-overview.md").read_text()
        for needle in (
            "systemctl status cedar-demo", "systemctl show cedar-demo.service",
            "   id\n", "Predict", "--no-ask-password", "InvocationID",
            "startup_id", "cedudo read-logs", "forbid-restart-outside-hours",
            "operators-restart", "developers-observe-demo",
            "absent from the manifest", "forbid-open-shell",
            "Simulated", "can still fail", "Command execution",
        ):
            self.assertIn(needle, text)


class RequirementsTests(unittest.TestCase):
    def test_cedarling_pinned_exactly(self):
        lines = [l.strip() for l in (ROOT / "requirements.txt").read_text().splitlines()
                 if l.strip() and not l.lstrip().startswith("#")]
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r"^cedarling-python==\d+\.\d+\.\d+$")

    def test_readme_installs_from_requirements_and_builds_archive(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("pip install -r requirements.txt", readme)
        self.assertNotRegex(readme, r"pip install cedarling-python")
        self.assertIn("./tools/build-cjar.sh", readme)
        self.assertLess(readme.index("./tools/build-cjar.sh"),
                        readme.index("policy/cedudo.cjar /opt/cedudo/cedudo.cjar"))
        self.assertIn("zip` and `unzip", readme)
        self.assertIn("does **not** parse the policies", readme)


class VerificationPathTests(unittest.TestCase):
    def test_readme_leads_through_all_three_checks(self):
        readme = (ROOT / "README.md").read_text()
        for cmd in ("./tools/install-demo-service.sh --check",
                    "python3 -m unittest discover -s tests",
                    "sudo ./tools/test-demo-service.sh"):
            self.assertIn(cmd, readme)
        self.assertIn("not a Cedudo installation check", readme)
        self.assertIn("PASSED WITH SKIPS", readme)
        self.assertLess(readme.index("install-demo-service.sh --check"),
                        readme.index("### 2. Create the installation directory"))

    def test_integration_script_reports_skips_and_supports_strict(self):
        text = (ROOT / "tools" / "test-demo-service.sh").read_text()
        for needle in ("--strict", "PASSED WITH SKIPS", "PASSED (nothing skipped)",
                       "RESULT: FAILED"):
            self.assertIn(needle, text)
        res = subprocess.run(["bash", str(ROOT / "tools" / "test-demo-service.sh"), "--bogus"],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 64)


class StudentIdentityTests(unittest.TestCase):
    def test_copyable_identity_blocks(self):
        readme = (ROOT / "README.md").read_text()
        for block in (
            "sudo -iu alice\nid\ncedudo read-logs\ncedudo explain restart-demo\nexit\n",
            "sudo -iu bob\nid\ncedudo explain restart-demo\ncedudo restart-demo\nexit\n",
        ):
            self.assertIn(block, readme)
        self.assertNotRegex(readme, r"(?m)^su - (alice|bob)\s*$")
        self.assertIn("never executes the operation", readme)
        self.assertIn("need **no password**", readme)
        self.assertLess(readme.index("need **no password**"),
                        readme.index("### Optional: passwords or SSH login"))


class OidcSeparationTests(unittest.TestCase):
    def test_oidc_moved_out_of_readme(self):
        readme = (ROOT / "README.md").read_text()
        oidc = (ROOT / "docs" / "oidc-login.md").read_text()
        for moved in ("add-apt-repository", "broker.conf", "authd-oidc", "keyboard-interactive"):
            self.assertNotIn(moved, readme)
        self.assertIn("docs/oidc-login.md", readme)
        self.assertIn("optional", readme.lower())
        self.assertIn("not needed for the local `alice` and `bob`", readme)
        self.assertLess(readme.index("### Optional: OIDC login"), readme.index("## 6. Troubleshooting"))
        self.assertIn("## Groups and authorization", oidc)
        self.assertIn("grants no Cedudo capability", oidc)
        self.assertIn("`developers`", oidc)
        self.assertIn("cedudo explain", oidc)

    def test_no_idp_specific_names(self):
        for path in (ROOT / "docs" / "oidc-login.md", ROOT / "README.md"):
            self.assertNotIn("gluu", path.read_text().lower(), path.name)
        self.assertIn("<IDP_USER_DOMAIN>", (ROOT / "docs" / "oidc-login.md").read_text())


class BusinessHoursChoicesTests(unittest.TestCase):
    def test_three_choices_and_exact_simulator_command(self):
        for name in ("README.md", "docs/demo-service.md"):
            text = (ROOT / name).read_text()
            self.assertIn("/opt/cedudo/venv/bin/python3 tools/cedudo-simulate.py restart-demo", text, name)
            self.assertIn("--hour 10", text)
            self.assertIn("Do not change the VM clock", text.replace("**", ""), name)
        guide = (ROOT / "docs" / "demo-service.md").read_text()
        for needle in ("### 1. Test now", "### 2. Simulate", "### 3. Run the real check",
                       "Last resort: pin the clock", "disposable", "snapshot"):
            self.assertIn(needle, guide)

    def test_clock_commands_only_in_the_fenced_procedure(self):
        guide = (ROOT / "docs" / "demo-service.md").read_text()
        self.assertEqual(guide.count("timedatectl set-ntp false"), 1)
        self.assertGreater(guide.index("timedatectl set-ntp false"),
                           guide.index("### Last resort: pin the clock"))
        for path in list(ROOT.glob("*.md")) + [ROOT / "docs" / "cedudo.md", ROOT / "docs" / "oidc-login.md"]:
            self.assertNotIn("timedatectl set-ntp", path.read_text(), path.name)

    def test_simulator_shebang_needs_explicit_venv_python(self):
        first = (ROOT / "tools" / "cedudo-simulate.py").read_text().splitlines()[0]
        self.assertEqual(first, "#!/usr/bin/env python3")


class ReadmeStructureTests(unittest.TestCase):
    README = (ROOT / "README.md").read_text()

    def test_section_order(self):
        order = ["## 1. Supported environment", "## 2. Administrator prerequisites",
                 "## 3. Install", "## 4. Verify", "## 5. Test as students",
                 "## 6. Troubleshooting", "## 7. Update and redeploy", "## 8. Uninstall"]
        positions = [self.README.index(h) for h in order]
        self.assertEqual(positions, sorted(positions))

    def test_links_to_guides(self):
        for link in ("workshop-overview.md", "docs/demo-service.md", "docs/oidc-login.md"):
            self.assertIn(f"]({link})", self.README.split("# Installing cedudo")[0])

    def test_troubleshooting_repaired(self):
        trouble = self.README[self.README.index("## 6. Troubleshooting"):self.README.index("## 7. Update")]
        self.assertNotIn("Script works for root but not regular users", trouble)
        self.assertIn("Deliberate", trouble)
        self.assertNotIn("gcc -o cedudo", self.README)
        self.assertIn("rerunning them", trouble)
        self.assertIn("./install-wrapper.sh", trouble)

    def test_cleanup_does_not_remove_clone(self):
        self.assertNotIn("/root/cedudo", self.README)
        uninstall = self.README[self.README.index("## 8. Uninstall"):]
        self.assertNotRegex(uninstall, r"rm -rf [~\$]?[\w/]*cedudo\b(?<!/opt/cedudo)")
        self.assertIn("Delete\nit yourself", uninstall)
        self.assertIn("readlink /usr/local/bin/cedudo", uninstall)


class ToolsReferenceTests(unittest.TestCase):
    DOC = (ROOT / "docs" / "tools.md").read_text()

    def test_every_tool_is_documented(self):
        tools = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "tools").iterdir())
                 if p.is_file()]
        tools += ["install-wrapper.sh", "cedudo-wrapper.c", "tests/test_static.py",
                  "demo-service/cedar-demo"]
        for tool in tools:
            name = tool.split("/", 1)[-1] if tool.startswith("tools/") else tool
            self.assertIn(name, self.DOC, f"{tool} missing from docs/tools.md")
        self.assertRegex(self.DOC, r"(?m)^## cedudo$")

    def test_documented_options_exist_in_scripts(self):
        self.assertIn("--check", (ROOT / "tools" / "install-demo-service.sh").read_text())
        self.assertIn("--strict", (ROOT / "tools" / "test-demo-service.sh").read_text())
        sim = (ROOT / "tools" / "cedudo-simulate.py").read_text()
        for flag in re.findall(r"`(--[a-z-]+)", self.DOC.split("## tools/cedudo-simulate.py")[1]
                               .split("## tools/install-demo-service.sh")[0]):
            if flag in ("--help",):
                continue
            self.assertIn(f'"{flag}"', sim, flag)

    def test_documented_exit_codes_match_cedudo(self):
        cedudo = load_cedudo()
        for name, code in (("EX_USAGE", 64), ("EX_UNAVAILABLE", 69), ("EX_SOFTWARE", 70),
                           ("EX_NOPERM", 77), ("EX_CONFIG", 78)):
            self.assertEqual(getattr(cedudo, name), code)
            self.assertRegex(self.DOC, rf"\| {code} \|")

    def test_linked_from_readme(self):
        self.assertIn("(docs/tools.md)", (ROOT / "README.md").read_text())


class DemoProgramTests(unittest.TestCase):
    PROGRAM = ROOT / "demo-service" / "cedar-demo"

    def test_messages_and_unique_startup_ids(self):
        mod = load_source("cedar_demo_mod", self.PROGRAM)
        ids = []
        for _ in range(2):
            with mock.patch("builtins.print") as out:
                self.assertEqual(mod.run(heartbeat_seconds=0.01, max_beats=2), 0)
            lines = [c.args[0] for c in out.call_args_list]
            self.assertRegex(lines[0], r"^cedar-demo startup startup_id=[0-9a-f]{12} ")
            self.assertRegex(lines[1], r"^cedar-demo heartbeat startup_id=[0-9a-f]{12} seq=1")
            self.assertRegex(lines[-1], r"^cedar-demo shutdown startup_id=")
            sid = re.search(r"startup_id=(\w+)", lines[0]).group(1)
            self.assertTrue(all(sid in line for line in lines))
            ids.append(sid)
        self.assertNotEqual(ids[0], ids[1])

    def test_sigterm_exits_cleanly(self):
        proc = subprocess.Popen(
            [sys.executable, str(self.PROGRAM)],
            stdout=subprocess.PIPE, text=True,
        )
        first = proc.stdout.readline()
        self.assertIn("startup startup_id=", first)
        time.sleep(0.2)
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("shutdown", out)
        self.assertIn("reason=SIGTERM", out)

    def test_no_network_code(self):
        text = self.PROGRAM.read_text()
        self.assertNotRegex(
            text, r"(?m)^\s*(import|from)\s+(socket|http|urllib|ssl)"
        )
        self.assertTrue(os.access(self.PROGRAM, os.X_OK))


class UnitAndScriptTests(unittest.TestCase):
    UNIT = (ROOT / "demo-service" / "cedar-demo.service").read_text()

    def setting(self, key):
        m = re.search(rf"^{key}=(.*)$", self.UNIT, re.M)
        self.assertIsNotNone(m, key)
        return m.group(1)

    def test_unit_identity_and_paths(self):
        self.assertEqual(self.setting("User"), "cedar-demo")
        self.assertEqual(self.setting("Group"), "cedar-demo")
        self.assertEqual(self.setting("ExecStart"), "/opt/cedar-demo/cedar-demo")
        install = (ROOT / "tools" / "install-demo-service.sh").read_text()
        self.assertIn("PROGRAM=\"${INSTALL_DIR}/cedar-demo\"", install)
        self.assertIn("INSTALL_DIR=/opt/cedar-demo", install)

    def test_unit_restrictions(self):
        for key, value in {
            "PrivateNetwork": "yes", "NoNewPrivileges": "yes",
            "ProtectSystem": "strict", "ProtectHome": "yes",
            "PrivateTmp": "yes", "KillSignal": "SIGTERM",
        }.items():
            self.assertEqual(self.setting(key), value)
        self.assertEqual(self.setting("RestrictAddressFamilies"), "AF_UNIX")
        self.assertEqual(self.setting("Restart"), "on-failure")

    def test_unit_is_commented(self):
        self.assertGreaterEqual(self.UNIT.count("\n#"), 8)

    def test_scripts_parse_and_are_executable(self):
        for name in ("install-demo-service.sh", "uninstall-demo-service.sh",
                     "test-demo-service.sh"):
            path = ROOT / "tools" / name
            self.assertTrue(os.access(path, os.X_OK), f"{name} not executable")
            subprocess.run(["bash", "-n", str(path)], check=True)
            if shutil.which("shellcheck"):
                subprocess.run(["shellcheck", "-S", "warning", str(path)], check=True)

    def test_install_script_properties(self):
        text = (ROOT / "tools" / "install-demo-service.sh").read_text()
        for needle in ('VERSION_ID:-}" != "24.04"', "--no-create-home",
                       "/usr/sbin/nologin", "-m 0755", "-m 0644",
                       "daemon-reload", "systemctl enable", "is-active",
                       "--check", "set -euo pipefail"):
            self.assertIn(needle, text)

    def test_uninstall_is_scoped(self):
        text = (ROOT / "tools" / "uninstall-demo-service.sh").read_text()
        self.assertNotIn("rm -rf", text)
        code = [l for l in text.splitlines() if not l.lstrip().startswith("#")]
        self.assertFalse([l for l in code if "/opt/cedudo" in l])
        for shared in ("alice", "bob", "developers", "operators"):
            self.assertNotRegex(text, rf"(userdel|groupdel)[^\n]*{shared}")

    def test_install_check_refuses_off_platform(self):
        if sys.platform.startswith("linux"):
            self.skipTest("only meaningful on a non-Ubuntu-24.04 host")
        res = subprocess.run(
            ["bash", str(ROOT / "tools" / "install-demo-service.sh"), "--check"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("error:", res.stderr)


class CedudoBehaviourTests(unittest.TestCase):
    """Mocked: trailing arguments cannot alter the executed command."""

    def run_main(self, argv, allowed=True, op_id="restart-demo"):
        cedudo = load_cedudo()
        operation = dict(MANIFEST[op_id])
        operation["action"] = (
            f'{operation["action_type"]}::"{operation["action_id"]}"'
        )
        account = mock.Mock(pw_name="bob", pw_uid=1001)
        context = {k: "x" for k in (
            "local_console", "interactive", "intruder_risk_level",
            "day_of_week", "date", "login_source_ip", "auth_method")}
        polluted = {"LD_PRELOAD": "/tmp/evil.so", "PATH": "/tmp/evil",
                    "SERVICE": "ssh"}
        with mock.patch.object(sys, "argv", ["cedudo", *argv]), \
             mock.patch.dict(os.environ, polluted), \
             mock.patch.object(cedudo, "invoking_user", return_value=(account, ["operators"])), \
             mock.patch.object(cedudo, "load_operation", return_value=operation) as load, \
             mock.patch.object(cedudo, "build_context", return_value=context), \
             mock.patch.object(cedudo, "initialize_cedarling"), \
             mock.patch.object(cedudo, "authorize", return_value=(allowed, ["p"])), \
             mock.patch.object(os, "chdir"), mock.patch.object(os, "umask"), \
             mock.patch.object(os, "execve") as execve:
            try:
                cedudo.main()
            except SystemExit as exc:
                return execve, load, exc.code
        return execve, load, None

    def test_trailing_args_ignored(self):
        for extra in (["--service", "ssh"], ["ssh.service"],
                      ["--unit=ssh.service", "-f", "--lines=999"]):
            execve, load, _ = self.run_main(["restart-demo", *extra])
            load.assert_called_once_with("restart-demo")
            path, argv, env = execve.call_args.args
            self.assertEqual(argv, MANIFEST["restart-demo"]["argv"])
            self.assertEqual(path, argv[0])
            self.assertNotIn("ssh.service", argv)
            self.assertEqual(argv[-1], "cedar-demo.service")

    def test_environment_sanitized(self):
        execve, _, _ = self.run_main(["read-logs", "extra"], op_id="read-logs")
        env = execve.call_args.args[2]
        for bad in ("LD_PRELOAD", "SERVICE"):
            self.assertNotIn(bad, env)
        self.assertNotIn("/tmp/evil", env["PATH"])
        self.assertEqual(env["SYSTEMD_PAGER"], "cat")

    def test_denied_does_not_execute(self):
        execve, _, code = self.run_main(["restart-demo"], allowed=False)
        execve.assert_not_called()
        self.assertEqual(code, 77)

    def test_no_shell_execution(self):
        text = (ROOT / "cedudo.py").read_text()
        self.assertNotIn("shell=True", text)
        self.assertNotIn("os.system", text)
        self.assertIn("os.execve(", text)

    def test_operation_id_validation(self):
        cedudo = load_cedudo()
        for bad in ("../../bin/bash", "restart-demo; /bin/bash", "Restart"):
            with self.assertRaises(SystemExit):
                cedudo.validate_operation_id(bad)


if __name__ == "__main__":
    unittest.main()
