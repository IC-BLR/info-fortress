import json
import random
from collections import Counter

SYSTEM_PROMPT = (
    "You are a news guardrail assistant. "
    "Return valid JSON only. "
    "The JSON must contain exactly these keys: "
    "verdict, confidence, sharing_policy, signals, evidence_spans, description, report. "
    "verdict must be one of: likely_false, uncertain, likely_true. "
    "sharing_policy must be one of: allow, caution, do_not_share. "
    "signals must be a JSON array of short strings. "
    "evidence_spans must be a JSON array of exact substrings copied from the provided TITLE or BODY. "
    "description must be 1 sentence. "
    "report must be 2-3 sentences. "
    "Use only the provided text. Do not invent sources, URLs, or facts."
)

FALSE_TRAIN_SCENARIOS = [
    ("Secret cure hidden by hospitals", "hospitals are hiding a miracle cure"),
    ("Government hiding alien attack tonight", "cities will be attacked tonight"),
    ("Bank hack rumor spreads on messaging apps", "every bank account will be emptied by midnight"),
    ("Free airline tickets for everyone this weekend", "the airline is giving free tickets to anyone who forwards the message"),
    ("Phone towers cause instant illness claim", "nearby phone towers are causing instant illness"),
    ("Water turns poisonous after midnight", "tap water becomes poisonous after midnight"),
    ("Army takeover announced in secret broadcast", "the army has taken over the government"),
    ("Hidden camera scam warning to all shoppers", "every mall restroom now has hidden cameras"),
    ("Celebrity death hoax resurfaces", "the actor has died"),
    ("Schools closed statewide tomorrow rumor", "all schools in the state are closed tomorrow"),
]

FALSE_EVAL_SCENARIOS = [
    ("Secret memo reveals banks will seize savings", "banks will seize savings next week"),
    ("Miracle herb erases cancer in 48 hours", "a miracle herb erases cancer in 48 hours"),
    ("Passport office deleting citizen records tonight", "the passport office is deleting citizen records tonight"),
    ("Free fuel coupon chain message spreads", "fuel stations are giving free fuel to anyone who forwards the message"),
    ("Vaccines secretly contain trackers claim", "vaccines secretly contain trackers"),
]

FALSE_TRAIN_PATTERNS = [
    {
        "body": "Sources say {claim}. Share now before this gets deleted. No official statement is cited.",
        "signals": ["anonymous_sourcing", "urgency_framing", "sensational_claim"],
        "evidence_spans": ["Sources say", "Share now before this gets deleted", "No official statement is cited"],
        "confidence": 0.89,
    },
    {
        "body": "Anonymous insiders say {claim}. Forward this message to everyone immediately. No official notice is attached.",
        "signals": ["anonymous_sourcing", "share_urge", "unsupported_claim"],
        "evidence_spans": ["Anonymous insiders say", "Forward this message to everyone immediately", "No official notice is attached"],
        "confidence": 0.88,
    },
    {
        "body": "A viral post claims {claim}, but it cites no regulator, no department notice, and no public record.",
        "signals": ["viral_rumor", "missing_primary_source", "unsupported_claim"],
        "evidence_spans": ["A viral post claims", "no regulator", "no public record"],
        "confidence": 0.86,
    },
    {
        "body": "This message says {claim}. Share before authorities remove it. No credible source is provided.",
        "signals": ["share_urge", "missing_primary_source", "alarmist_tone"],
        "evidence_spans": ["This message says", "Share before authorities remove it", "No credible source is provided"],
        "confidence": 0.87,
    },
    {
        "body": "The note says {claim} and urges readers to forward urgently, citing no report.",
        "signals": ["panic_message", "share_urge", "missing_evidence"],
        "evidence_spans": ["urges readers to forward urgently", "citing no report"],
        "confidence": 0.85,
    },
]

FALSE_EVAL_PATTERNS = [
    {
        "body": "A viral note claims {claim}. Share widely before it is removed. No official memo is attached.",
        "signals": ["viral_rumor", "share_urge", "missing_primary_source"],
        "evidence_spans": ["A viral note claims", "Share widely before it is removed", "No official memo is attached"],
        "confidence": 0.86,
    },
    {
        "body": "The message says {claim} and tells readers to forward it urgently, but no named authority is provided.",
        "signals": ["panic_message", "share_urge", "missing_primary_source"],
        "evidence_spans": ["tells readers to forward it urgently", "no named authority is provided"],
        "confidence": 0.84,
    },
]

UNCERTAIN_TRAIN_SCENARIOS = [
    ("Oil tanker attack report cites traders and early reports", "an oil tanker may have been attacked"),
    ("Bank collapse claim spreads online", "the bank may have collapsed"),
    ("Outbreak rumor spreads in city", "a major outbreak may have begun"),
    ("Ceasefire announcement attributed to unnamed diplomats", "a ceasefire may be announced within hours"),
    ("Power grid attack rumor trends overnight", "the national power grid may have been attacked"),
    ("Fuel shortage warning circulates before holiday", "an immediate fuel shortage may begin"),
    ("School poisoning alert shared by parents", "a poisoning incident may have happened at the school"),
    ("Exchange halt rumor rattles traders", "trading may be halted tomorrow"),
    ("Bridge collapse video linked to wrong city", "the bridge may have collapsed in the city"),
    ("Airport closure notice from unverified page", "the airport may close tonight"),
]

UNCERTAIN_EVAL_SCENARIOS = [
    ("Residents report loud blasts near border", "loud blasts may have occurred near the border"),
    ("Unofficial account says schools may close for heatwave", "schools may close for a heatwave"),
    ("Internet outage rumor spreads after storm", "the region may lose internet service tonight"),
    ("Hospital bed shortage warning circulates", "hospitals may run out of beds this week"),
    ("Rail strike screenshot spreads online", "a rail strike may begin tomorrow"),
]

UNCERTAIN_TRAIN_PATTERNS = [
    {
        "body": "Early reports say {claim}, but authorities have not confirmed the incident.",
        "signals": ["early_report", "missing_confirmation"],
        "evidence_spans": ["Early reports say", "authorities have not confirmed"],
        "confidence": 0.63,
    },
    {
        "body": "The post says {claim}, though no official statement is linked.",
        "signals": ["unverified_claim", "missing_primary_source"],
        "evidence_spans": ["The post says", "no official statement is linked"],
        "confidence": 0.60,
    },
    {
        "body": "Users are sharing that {claim}, but it relies on screenshots and no primary source.",
        "signals": ["screenshots_only", "missing_primary_source"],
        "evidence_spans": ["Users are sharing", "relies on screenshots", "no primary source"],
        "confidence": 0.58,
    },
    {
        "body": "Residents reported that {claim}, but no verified footage or named authority is provided.",
        "signals": ["eyewitness_only", "missing_confirmation"],
        "evidence_spans": ["Residents reported", "no verified footage", "named authority is provided"],
        "confidence": 0.57,
    },
    {
        "body": "An unverified page says {claim}, and the timing or location remains unclear.",
        "signals": ["unverified_source", "context_missing"],
        "evidence_spans": ["An unverified page says", "timing or location remains unclear"],
        "confidence": 0.56,
    },
]

UNCERTAIN_EVAL_PATTERNS = [
    {
        "body": "Local chatter suggests {claim}, but there is still no official confirmation.",
        "signals": ["local_chatter", "missing_confirmation"],
        "evidence_spans": ["Local chatter suggests", "no official confirmation"],
        "confidence": 0.59,
    },
    {
        "body": "The write-up suggests {claim}, yet the report gives no named authority and no exact timing.",
        "signals": ["missing_primary_source", "context_missing"],
        "evidence_spans": ["no named authority", "no exact timing"],
        "confidence": 0.58,
    },
]

TRUE_TRAIN_SCENARIOS = [
    ("Local weather office issues rainfall advisory", "heavy rainfall is expected this evening"),
    ("Museum opens new history wing", "the city museum opened a new history wing on Saturday"),
    ("Election commission publishes turnout figures", "the election commission published turnout figures district by district"),
    ("Central bank leaves policy rate unchanged", "the central bank kept the policy rate unchanged"),
    ("Health ministry launches vaccination drive", "the health ministry launched a vaccination drive starting Monday"),
    ("Rail operator publishes holiday timetable", "the rail operator released its holiday timetable"),
    ("City council approves budget after vote", "the city council approved the annual budget after a vote"),
    ("University confirms semester dates", "the university published the semester calendar"),
    ("Space agency schedules satellite launch", "the space agency announced a satellite launch window"),
    ("Court issues written order in land dispute", "the court released a written order in the land dispute"),
]

TRUE_EVAL_SCENARIOS = [
    ("Election dates announced on commission website", "the election commission published the full schedule on its official website"),
    ("Transit agency warns of delays after signal fault", "the transit agency warned of delays after a signal fault"),
    ("Airport authority opens new terminal gate", "the airport authority opened a new terminal gate"),
    ("Museum announces extended weekend hours", "the museum announced extended weekend hours"),
    ("University posts exam timetable", "the university posted the exam timetable on the student portal"),
]

TRUE_TRAIN_PATTERNS = [
    {
        "body": "According to the official statement, {claim}. The notice was published on the official website.",
        "signals": ["official_attribution", "published_notice"],
        "evidence_spans": ["official statement", "official website"],
        "confidence": 0.89,
    },
    {
        "body": "{claim}. The press release lists dates, locations, and contact details.",
        "signals": ["press_release", "specific_details"],
        "evidence_spans": ["press release", "dates, locations, and contact details"],
        "confidence": 0.87,
    },
    {
        "body": "{claim}. The update appears in the official bulletin with named officials and dates.",
        "signals": ["official_bulletin", "specific_details"],
        "evidence_spans": ["official bulletin", "named officials and dates"],
        "confidence": 0.86,
    },
    {
        "body": "{claim}. The decision was recorded in a public meeting and published in the formal notice.",
        "signals": ["public_record", "formal_notice"],
        "evidence_spans": ["public meeting", "formal notice"],
        "confidence": 0.85,
    },
    {
        "body": "{claim}. The agency posted the update on its website and social channels.",
        "signals": ["official_website", "cross_channel_publication"],
        "evidence_spans": ["posted the update on its website", "social channels"],
        "confidence": 0.84,
    },
]

TRUE_EVAL_PATTERNS = [
    {
        "body": "{claim}. The announcement appears on the agency's official website with schedule details.",
        "signals": ["official_attribution", "specific_details"],
        "evidence_spans": ["official website", "schedule details"],
        "confidence": 0.87,
    },
    {
        "body": "{claim}. The published notice names the authority and gives dates and locations.",
        "signals": ["named_authority", "specific_details"],
        "evidence_spans": ["published notice", "dates and locations"],
        "confidence": 0.85,
    },
]

def policy_for_label(label: str) -> str:
    if label == "likely_false":
        return "do_not_share"
    if label == "uncertain":
        return "caution"
    return "allow"

def description_for(label: str, signals):
    if label == "likely_false":
        return f"This item is assessed as likely false because the text shows cues such as {signals[0]} and {signals[1]}."
    if label == "uncertain":
        return f"This item is assessed as uncertain because the text suggests {signals[0]} and {signals[1]} without firm confirmation."
    return f"This item is assessed as likely true because the text includes {signals[0]} and {signals[1]}."

def report_for(title: str, label: str, evidence_spans, signals):
    if label == "likely_false":
        return (
            f"The item titled '{title}' contains credibility and manipulation warning signs. "
            f'Phrases like "{evidence_spans[0]}" and "{evidence_spans[1]}" indicate {signals[0]} and {signals[1]}. '
            f"This item should not be shared until a trusted primary source independently confirms it."
        )
    if label == "uncertain":
        return (
            f"The item titled '{title}' may refer to a real event, but the text is not sufficiently confirmed. "
            f'Phrases like "{evidence_spans[0]}" and "{evidence_spans[1]}" point to {signals[0]} and {signals[1]}. '
            f"This item should be handled cautiously until official confirmation appears."
        )
    return (
        f"The item titled '{title}' contains positive credibility cues. "
        f'Phrases like "{evidence_spans[0]}" and "{evidence_spans[1]}" support {signals[0]} and {signals[1]}. '
        f"This item can be shared, while normal source-checking is still recommended."
    )

def assistant_json(title: str, label: str, confidence: float, signals, evidence_spans):
    obj = {
        "verdict": label,
        "confidence": confidence,
        "sharing_policy": policy_for_label(label),
        "signals": signals,
        "evidence_spans": evidence_spans,
        "description": description_for(label, signals),
        "report": report_for(title, label, evidence_spans, signals),
    }
    return json.dumps(obj, ensure_ascii=False)

def make_rows(scenarios, patterns, label):
    rows = []
    for title, claim in scenarios:
        for pattern in patterns:
            body = pattern["body"].format(claim=claim)
            user_content = (
                "Assess this news item for credibility and sharing risk.\n\n"
                f"TITLE: {title}\n"
                f"BODY: {body}"
            )
            assistant_content = assistant_json(
                title=title,
                label=label,
                confidence=pattern["confidence"],
                signals=pattern["signals"],
                evidence_spans=pattern["evidence_spans"],
            )
            rows.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content},
                ]
            })
    return rows

def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def count_labels(rows):
    c = Counter()
    for row in rows:
        assistant = row["messages"][-1]["content"]
        verdict = json.loads(assistant)["verdict"]
        c[verdict] += 1
    return dict(c)

false_train = make_rows(FALSE_TRAIN_SCENARIOS, FALSE_TRAIN_PATTERNS, "likely_false")
uncertain_train = make_rows(UNCERTAIN_TRAIN_SCENARIOS, UNCERTAIN_TRAIN_PATTERNS, "uncertain")
true_train = make_rows(TRUE_TRAIN_SCENARIOS, TRUE_TRAIN_PATTERNS, "likely_true")

false_eval = make_rows(FALSE_EVAL_SCENARIOS, FALSE_EVAL_PATTERNS, "likely_false")
uncertain_eval = make_rows(UNCERTAIN_EVAL_SCENARIOS, UNCERTAIN_EVAL_PATTERNS, "uncertain")
true_eval = make_rows(TRUE_EVAL_SCENARIOS, TRUE_EVAL_PATTERNS, "likely_true")

train_rows = false_train + uncertain_train + true_train
eval_rows = false_eval + uncertain_eval + true_eval

random.Random(42).shuffle(train_rows)
random.Random(42).shuffle(eval_rows)

write_jsonl("qwen_guardrail_train.jsonl", train_rows)
write_jsonl("qwen_guardrail_eval.jsonl", eval_rows)

print("Wrote qwen_guardrail_train.jsonl:", len(train_rows), "rows")
print("Wrote qwen_guardrail_eval.jsonl:", len(eval_rows), "rows")
print("Train label counts:", count_labels(train_rows))
print("Eval label counts:", count_labels(eval_rows))
print("\nSample row:\n")
print(json.dumps(train_rows[0], indent=2, ensure_ascii=False))