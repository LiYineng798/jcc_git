from patch_note_service import parse_summary_markdown, validate_patch_note_payload


def test_parse_summary_markdown_recognizes_sections_and_change_types():
    parsed = parse_summary_markdown(
        '## 英雄调整\n\n'
        '- [buff] 亚托克斯：治疗 300 => 325\n'
        '- [nerf] 菲奥娜：真实伤害 40 => 37\n'
        '- [adjust] 法官：机制重做\n'
    )

    assert parsed[0] == {'type': 'section', 'title': '英雄调整'}
    assert parsed[1]['kind'] == 'buff'
    assert parsed[1]['label'] == '加强'
    assert parsed[1]['old_value'] == '亚托克斯：治疗 300'
    assert parsed[1]['new_value'] == '325'
    assert parsed[2]['kind'] == 'nerf'
    assert parsed[2]['label'] == '削弱'
    assert parsed[3]['kind'] == 'adjust'
    assert parsed[3]['text'] == '法官：机制重做'


def test_validate_patch_note_payload_rejects_invalid_status_and_source_url():
    payload, error = validate_patch_note_payload({
        'title': '17.4更新公告',
        'published_at': '2026-05-28',
        'summary_markdown': '- [buff] 亚托克斯：治疗 300 => 325',
        'status': 'online',
        'source_url': 'javascript:alert(1)',
    })

    assert payload is None
    assert error == '状态无效'


def test_validate_patch_note_payload_accepts_minimal_payload():
    payload, error = validate_patch_note_payload({
        'title': '17.4更新公告',
        'published_at': '2026-05-28',
        'summary_markdown': '- [buff] 亚托克斯：治疗 300 => 325',
        'status': 'published',
        'source_url': 'https://example.com/notice',
    })

    assert error is None
    assert payload['title'] == '17.4更新公告'
    assert payload['version'] == ''
    assert payload['status'] == 'published'
