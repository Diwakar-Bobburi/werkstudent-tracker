"""Relevance filter shared by all sources: is this a Werkstudent role in AI/ML/Data?"""
import re

from tracker import config


def has_term(text: str, terms: list[str]) -> bool:
    text = (text or "").lower()
    # word boundaries so "ai" doesn't match "maintenance" and "bi" doesn't match "mobile"
    return any(re.search(rf"(?<![a-zäöüß]){re.escape(t)}(?![a-zäöüß])", text) for t in terms)


def is_relevant(title: str, extra: str = "", student_hint: bool = False) -> bool:
    """`extra` = tags/occupation text; `student_hint` = source already says it's a student job."""
    is_student = student_hint or has_term(title, config.STUDENT_TERMS)
    return is_student and has_term(f"{title} {extra}", config.DOMAIN_TERMS)
