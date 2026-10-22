"""Which side a ring post is on, for the ranking only (todo/28, Marc 22 Oct: prefer Yes-side targets).

Hiding a Yes team's ring post also takes pro-Yes content off the feed, and the referendum pool goes to the winning
side only. The side NEVER reaches a report's detail text (rules §5.2.2, LS.6.5): reports stand on measured evidence
of automation alone, and every target still has to pass the same evidence bar. Cheap keyword rules, no LLM: the vote
phrases come read-only from swan_bot.targeting (its stance rules), plus the campaign tags and slogans each side's
bots use.
"""
import re

from swan_bot import targeting

YES_CUES = re.compile(r"#\w*yes\b|\b(favour|favor|back(ing)?|support(ing)?|for) (a )?yes\b|\byes (vote|campaign)\b|"
                      r"\bmy (mark|vote|tick)( still)? (goes|is) yes\b|protect ?kingstonia|\bvote yes\b", re.I)
NO_CUES = re.compile(r"#\w*no\b|\b(favour|favor|back(ing)?|support(ing)?|for) (a )?no\b|\bno (vote|campaign)\b|"
                     r"\bmy (mark|vote|tick)( still)? (goes|is) no\b|keep ?kingstonia ?open|\bvote no\b", re.I)
SIDES = ("yes", "no", "unclear")


def side(text):
    """'yes', 'no' or 'unclear' for a post's text: whichever side's vote phrases it uses more."""
    text = text or ""
    yes = len(targeting.FIRM_YES.findall(text)) + len(YES_CUES.findall(text))
    no = len(targeting.FIRM_NO.findall(text)) + len(targeting.LEAN_NO.findall(text)) + len(NO_CUES.findall(text))
    return "yes" if yes > no else "no" if no > yes else "unclear"
