# Premium Subscription System

## Overview
Your bot now has a premium subscription system with flexible pricing:

### Tiers & Pricing

**🆓 Free Tier**
- All minigames access
- Standard betting limits
- Basic daily rewards
- 5 RPS plays per 5 minutes
- Translate feature

**⭐ Premium Monthly - $9.99/month**
- AI Chat Bot access (`ghey`)
- 3x higher betting limits
- 3x daily rewards
- Unlimited RPS plays
- Premium badge & role
- Early access to new games

**👑 Premium Quarterly - $25/3 months**
- Same features as Monthly
- **Save $4.97** (16% discount!)
- Best value option

## Commands

**For Users:**
- `gpremium` - View all tiers and benefits
- `gmystatus` or `gsubscription` - Check your subscription status

**For Owner Only (you):**
- `ggrant @user premium 30` - Grant Premium for 30 days
- `ggrant @user vip 30` - Grant VIP for 30 days
- `grevoke @user` - Remove premium from user

## How It Works

1. **AI Chat Feature**: Now locked behind Premium/VIP subscription
   - When non-premium users try `ghey`, they see upgrade prompt
   - Premium+ users can chat unlimited

2. **Database**: New table `premium_users` tracks subscriptions
   - Stores tier, expiry date, and lifetime status
   - Auto-checks expiration

3. **Ready to Monetize**:
   - Set up Patreon/Ko-fi/PayPal for payments
   - When someone subscribes, use `ggrant @user premium 30`
   - Bot automatically manages access

## Next Steps to Add Premium Perks

To add premium betting limits to games, add this code before bet validation:

```python
# Check premium status for higher limits
premium_cog = self.bot.get_cog("Premium")
is_premium = premium_cog and await premium_cog.is_premium(ctx.author.id, "premium")
is_vip = premium_cog and await premium_cog.is_premium(ctx.author.id, "vip")

max_bet = 200000  # Free tier limit
if is_vip:
    max_bet = 1000000  # 5x for VIP
elif is_premium:
    max_bet = 400000  # 2x for Premium
```

## Revenue Potential

With fair pricing:
- 10 Premium subs = $49.90/month
- 5 VIP subs = $49.95/month
- Total from 15 users = ~$100/month

## Payment Processing Options

1. **Patreon** (Recommended)
   - Set up tiers matching your bot tiers
   - Automatic recurring billing
   - Built-in payment processing

2. **Ko-fi**
   - Monthly memberships
   - Lower fees than Patreon

3. **PayPal Subscriptions**
   - Direct control
   - Manual management needed

## Important Notes

- You manually grant access using `ggrant` command
- Bot automatically checks expiration daily
- Users get prompted to upgrade when trying premium features
- Fair pricing compared to other Discord bots
