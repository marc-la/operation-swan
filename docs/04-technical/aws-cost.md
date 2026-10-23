# AWS cost against the $200 credit (checked 2026-10-23)

One AWS account pays for the EC2 box and for Bedrock (Kimi, GLM, Claude), all from the $200 plan credit (upgrade of 23 Oct; was $99.67). `scripts/aws_cost.py` is the single place to read it:

```bash
.venv/bin/python scripts/aws_cost.py --ssh swan-ec2   # billed so far, ledger vs bill, projection to 2 Nov; writes data/aws_cost.json
```

It uses the IAM key in `.env` (`EC2_ACCESS_KEY`, never printed) through the `aws` CLI. It only reads.

## What the numbers mean
- **Billed** = Cost Explorer `RECORD_TYPE=Usage` (gross; the credit lines net every service to $0). It lags 12-24 h and the newest day is partial: read totals, not days.
- **Ledger** = the bot's own `data/llm_spend.json` on the box, in *padded* dollars (`config.LLM_PRICES`). Billed / ledger-price is about **0.82** (Kimi 21% and GLM 25% above the real price). The ledger charged nothing reliable on 21 Oct (2,369 Kimi calls, $0.13; billed $2.18), so the bot thinks it has about $2 more than it does.
- **Real Sydney prices** (USD per 1M tokens, in/out): Kimi K2.5 0.62/3.09, GLM-5 1.00/3.30, DeepSeek V3.2 0.64/1.91, Mistral Large 3 0.515/1.545. Claude global profiles bill at list (Haiku 4.5 1/5, Sonnet 4.6 3/15). DeepSeek and Mistral are the NPC lab's `LAB_DRAFTERS`: they run on Bedrock with `BEDROCK_API_KEY` (not free; $0.23 by 23 Oct) and have been in `LLM_PRICES` since 23 Oct, so the ledger counts them.
- CloudWatch `AWS/Bedrock` sees only Claude (Converse). Kimi/GLM/DeepSeek go through the mantle endpoint and show up only in the bill.
- EC2: t3.medium since 23 Oct 03:04 UTC is about $1.42/day with the Elastic IP and disk (t3.micro was $0.47). Unlimited-mode surplus billed: $0.035 in total.

## Daily floor (23 Oct)
`config.LLM_DAILY_FLOOR_USD` = $12 ledger dollars a day: the allowance through any budget day is never below 12 x days so far, still capped by `LLM_BUDGET_USD`. The bot spends ~$6-9 a day, and the old weighted share ($6.80 for 21-25 Oct) left no margin: on 23 Oct Kimi was walled off from ~06:30 Sydney, Gemini was out of quota, and drafts found no model for ~7 h (hourly live writes fell from ~130 to 4-8). Worst case at the floor every day: 13 x 12 = $156 ledger, about $128 billed.

## Status (script prints OK / WATCH / OVER)
OK = even if the bot spends the whole `LLM_BUDGET_USD`, we finish under 90% of the credit. 23 Oct: OK. At the recent pace (~$5.85 ledger/day) about $79 in total; spending the full budget about $161. Resources keep billing after 2 Nov: stop the instance and release the Elastic IP then.

## IAM permissions to add (inline policy on `ctn-user`)
Console: IAM > Users > ctn-user > Permissions > Add permissions > **Create inline policy** > JSON. These are single actions, so they are not in the "attach managed policies" list.
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "freetier:GetAccountPlanState",
      "ce:GetCostForecast",
      "budgets:ModifyBudget",
      "budgets:ViewBudget"
    ],
    "Resource": "*"
  }]
}
```
`GetAccountPlanState` returns the remaining credit and its expiry; `GetCostForecast` is AWS's own projection (the "$194" in the billing console); the budgets pair lets us create the spend alert (none exists).
