"""Policy/lint helpers for cron jobs and scheduled-run maintenance.

This module intentionally stays lightweight and dependency-free. It provides
small, auditable checks for the scheduler path: flag risky job shapes before
execution, preserve findings in run metadata, and let operator-facing tools build
maintenance reports without waking an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class CronPolicyFinding:
    """One policy/lint finding for a cron job."""

    code: str
    severity: str
    message: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def lint_cron_job(job: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return non-blocking policy/lint findings for a cron job.

    The scheduler treats these as audit metadata, not as hard failures. Blocking
    checks (for example prompt-injection scanning) remain in the execution path
    where they already have full context.
    """
    findings: List[CronPolicyFinding] = []

    job_id = str(job.get("id") or "<unknown>")
    no_agent = bool(job.get("no_agent"))
    script = job.get("script")
    prompt = job.get("prompt")
    deliver = job.get("deliver", "local")

    if no_agent and not _has_text(script):
        findings.append(
            CronPolicyFinding(
                "cron.no_agent_without_script",
                "error",
                f"Job {job_id} sets no_agent=True but has no script.",
            )
        )

    if not no_agent and not (_has_text(prompt) or _has_text(script) or job.get("skills")):
        findings.append(
            CronPolicyFinding(
                "cron.empty_agent_inputs",
                "warning",
                f"Job {job_id} has no prompt, script, or skills; it is likely to produce an empty run.",
            )
        )

    if deliver != "local" and not (_has_text(prompt) or _has_text(script) or no_agent or job.get("skills")):
        findings.append(
            CronPolicyFinding(
                "cron.delivery_without_content_source",
                "warning",
                f"Job {job_id} is configured for delivery but has no obvious content source.",
            )
        )

    if job.get("context_from") and not isinstance(job.get("context_from"), list):
        findings.append(
            CronPolicyFinding(
                "cron.context_from_not_list",
                "warning",
                f"Job {job_id} has malformed context_from; expected a list of upstream job IDs.",
            )
        )

    if job.get("workdir") and not _has_text(job.get("workdir")):
        findings.append(
            CronPolicyFinding(
                "cron.blank_workdir",
                "warning",
                f"Job {job_id} has a blank workdir field; clear it instead of storing whitespace.",
            )
        )

    return [finding.as_dict() for finding in findings]


def summarize_policy_findings(findings: Iterable[Dict[str, str]]) -> str:
    """Human-readable compact summary for logs/output docs."""
    parts = []
    for finding in findings or []:
        code = finding.get("code", "policy")
        severity = finding.get("severity", "info")
        message = finding.get("message", "")
        parts.append(f"- [{severity}] {code}: {message}")
    return "\n".join(parts)
