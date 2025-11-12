import asyncio
import importlib.machinery
import importlib.util
import sys
from types import SimpleNamespace

# Load blackjack module by path
loader = importlib.machinery.SourceFileLoader('blackjack_mod', r'c:\Users\user\discord bot.py\cogs\blackjack.py')
spec = importlib.util.spec_from_loader(loader.name, loader)
blackjack = importlib.util.module_from_spec(spec)
# Ensure workspace root is on sys.path so relative imports (utils.*) resolve
sys.path.insert(0, r'c:\Users\user\discord bot.py')
loader.exec_module(blackjack)

# Monkeypatch async DB helpers in the module
user_state = {'mora': 1000}

async def fake_get_user_data(user_id):
    return dict(user_state)

async def fake_update_user_data(user_id, mora=None, **kwargs):
    if mora is not None:
        user_state['mora'] = mora
    return True

blackjack.get_user_data = fake_get_user_data
blackjack.update_user_data = fake_update_user_data

# Dummy ctx and message objects
class DummyMessage:
    def __init__(self):
        self.edits = []
    async def edit(self, *args, **kwargs):
        self.edits.append((args, kwargs))

class DummyAuthor:
    def __init__(self, id=123, name='Tester'):
        self.id = id
        self.display_name = name

class DummyCtx:
    def __init__(self):
        self.author = DummyAuthor()

class DummyCog:
    def __init__(self):
        self.active_games = set()

async def run_case(name, player_cards, dealer_cards, bet=100, do_hit=True):
    # reset user state
    user_state['mora'] = 1000
    # emulate reservation of bet which blackjack() would do prior to creating the view
    user_state['mora'] -= bet
    ctx = DummyCtx()
    cog = DummyCog()
    deck = blackjack.make_deck()
    # ensure deck doesn't interfere; we'll not pop from it for deterministic steps
    # starting balance before reservation (we subtracted bet above), compute it
    start_balance = user_state['mora'] + bet
    view = blackjack.BlackjackView(ctx, bet, deck, player_cards.copy(), dealer_cards.copy(), reserved_total=bet, cog=cog, start_balance=start_balance)
    view.message = DummyMessage()
    # simulate immediate conditions
    # If player already has 21 at start, blackjack() handles that earlier path; here we test flows via methods
    print(f"--- Test: {name}")
    # If player needs to hit to reach 21, call _award_hand_immediately by simulating a hit that makes pv==21
    pv = blackjack.hand_value(view.current_hand()['cards'])
    dv = blackjack.hand_value(view.dealer)
    print(f"Start balance: {user_state['mora']}, player value {pv}, dealer value {dv}")
    # If player already 21, emulate immediate award
    if pv == 21:
        await view._award_hand_immediately(view.current_hand())
        # call finish_and_settle
        await view.finish_and_settle()
    else:
        if do_hit:
            # attempt hitting to 21: append a card that makes value 21 if possible
            for r in blackjack.RANKS[::-1]:
                test_card = r + blackjack.SUITS[0]
                new_pv = blackjack.hand_value(view.current_hand()['cards'] + [test_card])
                if new_pv == 21:
                    view.current_hand()['cards'].append(test_card)
                    # simulate hit flow
                    await view._award_hand_immediately(view.current_hand())
                    await view.finish_and_settle()
                    break
            else:
                # fallback: just finish and settle
                await view.finish_and_settle()
        else:
            # don't hit; just finish and settle to test push scenarios
            await view.finish_and_settle()

    print(f"End balance: {user_state['mora']}")
    print(f"Message edits: {len(view.message.edits)}\n")

async def main():
    # Case: player hits to 21, dealer has 20 -> player should win
    await run_case('player hits to 21 vs dealer 20', ['10♠', 'A♠'], ['K♣', 'Q♣'], bet=100)
    # Case: push both 20
    await run_case('push both 20', ['10♠', 'Q♠'], ['10♣', 'Q♣'], bet=100, do_hit=False)
    # Case: dealer busts
    await run_case('dealer busts', ['10♠', '9♠'], ['K♣', '9♣', '5♣'], bet=100)

if __name__ == '__main__':
    asyncio.run(main())
