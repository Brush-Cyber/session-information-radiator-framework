import re
from difflib import SequenceMatcher
from sirm.models import ForgeItem, WorkOrder, _now

PRIORITY_SIGNALS = {
    1: [r"\burgent\b", r"\bcritical\b", r"\bemergency\b", r"\boutage\b", r"\bincident\b", r"\bsev[- ]?1\b", r"\bp0\b", r"\bp1\b"],
    2: [r"\bhigh\b.*\bpriority\b", r"\bimportant\b", r"\basap\b", r"\bblocking\b", r"\bblocker\b", r"\bsev[- ]?2\b", r"\bp2\b"],
    3: [r"\bmedium\b", r"\bnormal\b", r"\bstandard\b"],
    4: [r"\blow\b.*\bpriority\b", r"\bnice.to.have\b", r"\bwhen.possible\b", r"\bbacklog\b", r"\bsomeday\b"],
    5: [r"\bwish\b", r"\bmaybe\b", r"\bexplore\b", r"\bconsider\b"],
}

TYPE_PATTERNS = {
    "security": [r"\bsecurity\b", r"\bvulnerabilit", r"\bcve\b", r"\bexploit\b", r"\binjection\b", r"\bxss\b", r"\bcsrf\b", r"\bauth\s*bypass\b", r"\bencrypt", r"\bfirewall\b"],
    "bug": [r"\bbug\b", r"\bfix\b", r"\bbroken\b", r"\bcrash", r"\berror\b", r"\bexception\b", r"\bfailure\b", r"\bregression\b", r"\bnot working\b"],
    "feature": [r"\bfeature\b", r"\badd\b", r"\bimplement\b", r"\bcreate\b", r"\bbuild\b", r"\bnew\b", r"\benhance", r"\bimprove\b"],
    "infrastructure": [r"\binfra", r"\bdeploy", r"\bci/?cd\b", r"\bpipeline\b", r"\bdocker\b", r"\bkubernetes\b", r"\bscaling\b", r"\bmonitoring\b", r"\bserver\b"],
    "refactor": [r"\brefactor\b", r"\bcleanup\b", r"\breorganize\b", r"\brestructure\b", r"\btech debt\b", r"\barchitect"],
    "research": [r"\bresearch\b", r"\bspike\b", r"\binvestigate\b", r"\bpoc\b", r"\bproof of concept\b", r"\bprototype\b", r"\bevaluate\b"],
}

TYPE_TO_ROLE = {
    "security": "quality_overlay",
    "bug": "line_worker",
    "feature": "line_worker",
    "infrastructure": "line_worker",
    "refactor": "line_worker",
    "research": "line_manager",
    "unknown": "line_worker",
}

TYPE_TO_STAGE = {
    "security": "code",
    "bug": "code",
    "feature": "plan",
    "infrastructure": "operate",
    "refactor": "code",
    "research": "plan",
    "unknown": "plan",
}

BATCH_SEPARATORS = [
    r"\n---+\n",
    r"\n\n\n+",
    r"\n\d+\.\s+",
    r"\n[-*]\s+(?=[A-Z])",
]


def _extract_title(text):
    text = text.strip()
    lines = text.split("\n")
    first_line = lines[0].strip()
    first_line = re.sub(r"^[\d]+[.)]\s*", "", first_line)
    first_line = re.sub(r"^[-*]\s*", "", first_line)
    first_line = re.sub(r"^#+\s*", "", first_line)
    if len(first_line) > 120:
        sentences = re.split(r"[.!?]\s+", first_line)
        if sentences:
            first_line = sentences[0]
    if len(first_line) > 120:
        first_line = first_line[:117] + "..."
    return first_line.strip()


def _extract_description(text):
    lines = text.strip().split("\n")
    if len(lines) > 1:
        desc_lines = lines[1:]
        desc = "\n".join(l.strip() for l in desc_lines).strip()
        return desc
    return ""


def _detect_type(text):
    lower = text.lower()
    scores = {}
    for type_name, patterns in TYPE_PATTERNS.items():
        count = 0
        for pattern in patterns:
            if re.search(pattern, lower):
                count += 1
        if count > 0:
            scores[type_name] = count
    if not scores:
        return "unknown"
    return max(scores, key=scores.get)


def _detect_priority(text):
    lower = text.lower()
    for priority in sorted(PRIORITY_SIGNALS.keys()):
        for pattern in PRIORITY_SIGNALS[priority]:
            if re.search(pattern, lower):
                return priority
    return 3


def _extract_tags(text):
    lower = text.lower()
    tags = set()
    tag_patterns = {
        "api": r"\bapi\b",
        "database": r"\bdatabase\b|\bdb\b|\bsql\b|\bpostgres",
        "frontend": r"\bfrontend\b|\bui\b|\bux\b|\bcss\b|\breact\b",
        "backend": r"\bbackend\b|\bserver\b|\bflask\b|\bdjango\b",
        "auth": r"\bauth\b|\blogin\b|\bpassword\b|\boauth\b|\bsso\b",
        "performance": r"\bperformance\b|\bslow\b|\boptimiz|\bcache\b|\blatency\b",
        "testing": r"\btest\b|\btesting\b|\bcoverage\b|\bunit test\b|\be2e\b",
        "documentation": r"\bdoc\b|\bdocumentation\b|\breadme\b|\bguide\b",
        "mobile": r"\bmobile\b|\bios\b|\bandroid\b|\bapp\b",
        "integration": r"\bintegrat\b|\bwebhook\b|\bthird.party\b",
        "billing": r"\bbilling\b|\bpayment\b|\bsubscription\b|\bstripe\b|\brevenue\b",
        "compliance": r"\bcompliance\b|\baudit\b|\bsoc\b|\bgdpr\b|\bhipaa\b",
        "migration": r"\bmigrat\b|\bupgrade\b|\bport\b",
        "devops": r"\bdevops\b|\bci\b|\bcd\b|\bdeploy\b|\brelease\b",
    }
    for tag, pattern in tag_patterns.items():
        if re.search(pattern, lower):
            tags.add(tag)
    return sorted(tags)


def _similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _split_batch(text):
    text = text.strip()
    if not text:
        return []

    for sep in BATCH_SEPARATORS:
        parts = re.split(sep, text)
        cleaned = [p.strip() for p in parts if p.strip() and len(p.strip()) > 10]
        if len(cleaned) > 1:
            return cleaned

    paragraphs = re.split(r"\n\n+", text)
    cleaned = [p.strip() for p in paragraphs if p.strip() and len(p.strip()) > 10]
    if len(cleaned) > 1:
        return cleaned

    return [text]


class FoundryEngine:
    def __init__(self, store):
        self.store = store

    def intake(self, raw_text, source="manual"):
        item = ForgeItem(
            raw_input=raw_text.strip(),
            source=source,
            status="raw",
        )
        self.store.save_forge_item(item)
        return item

    def batch_intake(self, text_dump, source="data_dump"):
        chunks = _split_batch(text_dump)
        items = []
        for chunk in chunks:
            item = self.intake(chunk, source=source)
            items.append(item)
        return items

    def smelt(self, item):
        item.status = "smelting"
        raw = item.raw_input
        notes = []

        title = _extract_title(raw)
        if title:
            item.extracted_title = title
            notes.append(f"Extracted title: '{title}'")
        else:
            item.extracted_title = raw[:80]
            notes.append("No clear title found, using first 80 chars")

        desc = _extract_description(raw)
        if desc:
            item.extracted_description = desc
            notes.append(f"Extracted description ({len(desc)} chars)")
        else:
            item.extracted_description = raw
            notes.append("Using full raw input as description")

        detected_type = _detect_type(raw)
        item.extracted_type = detected_type
        notes.append(f"Detected type: {detected_type}")

        priority = _detect_priority(raw)
        item.suggested_priority = priority
        notes.append(f"Suggested priority: P{priority}")

        item.suggested_role = TYPE_TO_ROLE.get(detected_type, "line_worker")
        item.suggested_stage = TYPE_TO_STAGE.get(detected_type, "plan")

        tags = _extract_tags(raw)
        item.suggested_tags = tags
        if tags:
            notes.append(f"Extracted tags: {', '.join(tags)}")

        from sirm.orchestration import PRODUCT_LINES
        lower_raw = raw.lower()
        for line_name, line_info in PRODUCT_LINES.items():
            for proj_name in line_info["projects"]:
                if proj_name.lower() in lower_raw:
                    item.suggested_product_line = line_name
                    item.suggested_project = proj_name
                    notes.append(f"Matched product line: {line_name}, project: {proj_name}")
                    break
            if item.suggested_product_line:
                break

        if not item.suggested_product_line:
            product_keywords = {
                "Core Products": ["product", "revenue", "customer", "user", "plan", "pacer", "guru", "builder", "raci", "kip"],
                "Platform & Infrastructure": ["platform", "infrastructure", "cicd", "pipeline", "deploy", "migration", "orion", "reliability"],
                "Strategy & Governance": ["strategy", "governance", "roadmap", "style guide", "billing", "forge", "revenue engine"],
            }
            for line_name, keywords in product_keywords.items():
                for kw in keywords:
                    if kw in lower_raw:
                        item.suggested_product_line = line_name
                        notes.append(f"Inferred product line from keyword '{kw}': {line_name}")
                        break
                if item.suggested_product_line:
                    break

        existing_tasks = self.store.list_tasks()
        duplicates = []
        for task in existing_tasks:
            if task.status == "done":
                continue
            sim = _similarity(item.extracted_title, task.title)
            if sim >= 0.6:
                duplicates.append({
                    "id": task.id,
                    "title": task.title,
                    "similarity": round(sim * 100),
                    "status": task.status,
                })
        if duplicates:
            item.related_existing = sorted(duplicates, key=lambda x: x["similarity"], reverse=True)[:10]
            notes.append(f"Found {len(duplicates)} similar existing work orders")

        confidence = 20
        if item.extracted_title and len(item.extracted_title) > 5:
            confidence += 15
        if item.extracted_description and len(item.extracted_description) > 20:
            confidence += 15
        if detected_type != "unknown":
            confidence += 15
        if item.suggested_product_line:
            confidence += 15
        if not duplicates:
            confidence += 10
        if tags:
            confidence += 10
        item.confidence_score = min(100, confidence)
        notes.append(f"Confidence score: {item.confidence_score}")

        for note_text in notes:
            item.add_note(note_text)

        item.status = "refined"
        self.store.save_forge_item(item)
        return item

    def gate(self, item):
        gates = []

        has_title = bool(item.extracted_title) and len(item.extracted_title) > 5
        gates.append({
            "name": "Clarity",
            "passed": has_title and len(item.extracted_description) > 20,
            "detail": f"Title: {'yes' if has_title else 'no'} ({len(item.extracted_title)} chars), Description: {len(item.extracted_description)} chars",
        })

        has_duplicate = any(d.get("similarity", 0) >= 80 for d in item.related_existing)
        gates.append({
            "name": "Uniqueness",
            "passed": not has_duplicate,
            "detail": f"{'High similarity duplicate found' if has_duplicate else 'No close duplicates'} ({len(item.related_existing)} related items)",
        })

        concept_markers = len(re.findall(r"(?:^|\n)(?:\d+[.)]\s|[-*]\s|#{1,3}\s)", item.raw_input))
        too_broad = concept_markers > 5 and len(item.raw_input) > 1000
        gates.append({
            "name": "Scope",
            "passed": not too_broad,
            "detail": f"{'Too broad — consider splitting' if too_broad else 'Scope is focused'} ({concept_markers} concept markers)",
        })

        gates.append({
            "name": "Alignment",
            "passed": bool(item.suggested_product_line),
            "detail": f"Product line: {item.suggested_product_line or 'not identified'}",
        })

        gates.append({
            "name": "Priority",
            "passed": item.suggested_priority > 0 and item.suggested_priority <= 5,
            "detail": f"Priority: P{item.suggested_priority}",
        })

        gates.append({
            "name": "Readiness",
            "passed": item.confidence_score >= 40,
            "detail": f"Confidence: {item.confidence_score}%",
        })

        item.gate_results = gates
        passed = sum(1 for g in gates if g["passed"])
        item.gate_score = round((passed / len(gates)) * 100) if gates else 0
        item.status = "gated"
        self.store.save_forge_item(item)
        return item

    def forge(self, item):
        if item.status == "forged":
            return None
        if item.status not in ("gated", "refined"):
            return None
        if item.gate_score < 50:
            return None

        work_order = WorkOrder(
            title=item.extracted_title or item.raw_input[:80],
            description=item.extracted_description or item.raw_input,
            status="backlog",
            stage=item.suggested_stage or "plan",
            role=item.suggested_role or "line_worker",
            priority=item.suggested_priority or 3,
            tags=item.suggested_tags or [],
        )

        if item.suggested_product_line:
            work_order.tags = list(set(work_order.tags + [f"foundry/{item.suggested_product_line}"]))
        if item.suggested_project:
            work_order.tags = list(set(work_order.tags + [f"project/{item.suggested_project}"]))

        work_order.tags = list(set(work_order.tags + ["foundry-forged"]))

        work_order.add_activity(
            "forged",
            f"Created from Foundry item {item.id}. Confidence: {item.confidence_score}%, Gate score: {item.gate_score}%. Source: {item.source}",
            actor="foundry",
        )

        self.store.save_task(work_order)

        item.work_order_id = work_order.id
        item.status = "forged"
        item.add_note(f"Forged into WorkOrder {work_order.id}: '{work_order.title}'")
        self.store.save_forge_item(item)

        return work_order

    def reject(self, item, reason=""):
        item.status = "rejected"
        item.rejection_reason = reason
        item.add_note(f"Rejected: {reason}" if reason else "Rejected")
        self.store.save_forge_item(item)
        return item

    def auto_process(self, raw_text, source="manual"):
        item = self.intake(raw_text, source=source)
        item = self.smelt(item)
        item = self.gate(item)
        return item

    def get_pipeline_stats(self):
        items = self.store.list_forge_items()
        stats = {"raw": 0, "smelting": 0, "refined": 0, "gated": 0, "forged": 0, "rejected": 0}
        total_confidence = 0
        total_gate = 0
        gated_count = 0

        for item in items:
            stats[item.status] = stats.get(item.status, 0) + 1
            total_confidence += item.confidence_score
            if item.gate_score > 0:
                total_gate += item.gate_score
                gated_count += 1

        return {
            "total": len(items),
            "by_status": stats,
            "avg_confidence": round(total_confidence / len(items)) if items else 0,
            "avg_gate_score": round(total_gate / gated_count) if gated_count else 0,
        }
