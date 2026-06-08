from cron.policy import lint_cron_job, summarize_policy_findings


def test_lint_no_agent_requires_script():
    findings = lint_cron_job({"id": "job1", "no_agent": True, "script": ""})

    assert findings
    assert findings[0]["code"] == "cron.no_agent_without_script"
    assert findings[0]["severity"] == "error"


def test_lint_empty_agent_inputs_warns():
    findings = lint_cron_job({"id": "job2", "no_agent": False, "deliver": "local"})

    assert any(f["code"] == "cron.empty_agent_inputs" for f in findings)


def test_summary_formats_findings():
    text = summarize_policy_findings([
        {"code": "cron.empty_agent_inputs", "severity": "warning", "message": "empty"}
    ])

    assert "[warning] cron.empty_agent_inputs: empty" in text
