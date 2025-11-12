import asyncio
import pytest
from utils.database import award_achievement, get_user_achievements


@pytest.mark.asyncio
async def test_award_and_list_achievement():
    user_id = 999999999
    # award an achievement
    ok = await award_achievement(user_id, 'test_ach', 'Test Achievement', 'This is a test achievement')
    assert ok is True or ok is None

    rows = await get_user_achievements(user_id)
    keys = [r['key'] for r in rows]
    assert 'test_ach' in keys
