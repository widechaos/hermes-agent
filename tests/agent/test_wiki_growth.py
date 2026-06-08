from pathlib import Path

from agent.wiki_growth import capture_turn_candidate, should_capture_turn


def test_should_capture_stable_signal():
    assert should_capture_turn(
        user_message="以后我说关屏，你要主动执行这个约定",
        assistant_response="记住了",
        platform="feishu",
    )


def test_should_skip_cron_and_lean():
    assert not should_capture_turn(
        user_message="以后记住这个规则",
        assistant_response="ok",
        platform="cron",
    )
    assert not should_capture_turn(
        user_message="以后记住这个规则",
        assistant_response="ok",
        platform="feishu",
        lean_mode=True,
    )


def test_capture_turn_candidate_writes_queue(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = capture_turn_candidate(
        cfg={"wiki_growth": {"enabled": True, "vault_path": str(vault)}},
        user_message="以后我说关屏，就是关闭显示器这个稳定约定",
        assistant_response="好，已按 Wiki 候选捕获。",
        session_id="sess1",
        platform="feishu",
        model="test-model",
        turn_exit_reason="final_response",
    )

    assert path is not None
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "状态: shadow-trial" in text
    assert "以后我说关屏" in text
    assert "待评估动作" in text


def test_capture_disabled_by_default(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    path = capture_turn_candidate(
        cfg={"wiki_growth": {"enabled": False, "vault_path": str(vault)}},
        user_message="以后我说关屏，就是关闭显示器这个稳定约定",
        assistant_response="ok",
        session_id="sess1",
        platform="feishu",
        model="test-model",
    )

    assert path is None
