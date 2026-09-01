#!/usr/bin/env python3
"""Unit tests for remediation policy classification and Mode B split."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "neuro-san" / "coded_tools" / "fossa_remediation"))

from remediation_policy import (  # noqa: E402
    RISK_AUTO,
    RISK_HUMAN,
    classify_action,
    classify_actions,
    clear_policy_cache,
)


class RemediationPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_policy_cache()

    def test_patch_bump_is_auto(self) -> None:
        action = {
            "action": "bump_version",
            "group_id": "org.apache.logging.log4j",
            "artifact_id": "log4j-core",
            "current_version": "2.17.1",
            "target_version": "2.17.2",
        }
        classified = classify_action(action)
        self.assertEqual(classified["risk"], RISK_AUTO)

    def test_major_bump_requires_human(self) -> None:
        action = {
            "action": "bump_version",
            "group_id": "com.fasterxml.jackson.core",
            "artifact_id": "jackson-databind",
            "current_version": "2.15.0",
            "target_version": "3.0.0",
        }
        classified = classify_action(action)
        self.assertEqual(classified["risk"], RISK_HUMAN)
        self.assertIn("major version bump", classified["risk_reason"])

    def test_spring_boot_bom_requires_human(self) -> None:
        action = {
            "action": "bump_version",
            "group_id": "org.springframework.boot",
            "artifact_id": "spring-boot-dependencies",
            "current_version": "3.2.0",
            "target_version": "3.2.5",
        }
        classified = classify_action(action)
        self.assertEqual(classified["risk"], RISK_HUMAN)
        self.assertIn("BOM", classified["risk_reason"])

    def test_artifact_glob_bom(self) -> None:
        action = {
            "action": "bump_version",
            "group_id": "io.micrometer",
            "artifact_id": "micrometer-bom",
            "current_version": "1.12.0",
            "target_version": "1.12.1",
        }
        classified = classify_action(action)
        self.assertEqual(classified["risk"], RISK_HUMAN)

    def test_remove_requires_human(self) -> None:
        action = {
            "action": "remove",
            "group_id": "commons-collections",
            "artifact_id": "commons-collections",
        }
        classified = classify_action(action)
        self.assertEqual(classified["risk"], RISK_HUMAN)
        self.assertIn("remove", classified["risk_reason"])

    def test_classify_actions_split(self) -> None:
        actions = [
            {
                "action": "bump_version",
                "group_id": "org.apache.logging.log4j",
                "artifact_id": "log4j-core",
                "current_version": "2.17.1",
                "target_version": "2.17.2",
            },
            {
                "action": "bump_version",
                "group_id": "org.hibernate",
                "artifact_id": "hibernate-core",
                "current_version": "5.6.15.Final",
                "target_version": "5.6.15.Final",
            },
        ]
        auto, human = classify_actions(actions)
        self.assertEqual(len(auto), 1)
        self.assertEqual(auto[0]["artifact_id"], "log4j-core")
        self.assertEqual(len(human), 1)
        self.assertEqual(human[0]["artifact_id"], "hibernate-core")


if __name__ == "__main__":
    unittest.main()
