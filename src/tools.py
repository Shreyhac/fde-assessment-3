"""Shreyansh Arora | 24bcs10252. Read-only evidence tools."""
from datetime import date
import re
from decimal import Decimal, InvalidOperation
from src import data_access as db
from src.vendor_client import get_vendor_risk


def clean_records(frame):
    return frame.fillna('').to_dict('records')


class Tools:
    def __init__(self):
        self.calls = []
        self.cache = {}

    def call(self, name, key, fn):
        cache_key = (name, str(key))
        if cache_key not in self.cache:
            self.calls.append(name)
            self.cache[cache_key] = fn()
        return self.cache[cache_key]

    def budget(self, requester):
        def run():
            employee = next((e for e in clean_records(db.load_employees()) if e['employee_id'] == requester), None)
            budget = next((b for b in clean_records(db.load_budgets()) if employee and b['department'] == employee['department']), None)
            return {'employee': employee, 'budget': budget}
        return self.call('budget_lookup', requester, run)

    def catalog(self, request):
        def run():
            matches = [r for r in clean_records(db.load_software_catalog()) if str(r['status']).lower().startswith('approved') and
                    (r['category'].lower() == str(request.get('category', '')).lower() or
                     r['vendor_name'].lower() == str(request.get('vendor_name', '')).lower() or
                     r['product_name'].lower() == str(request.get('product_name', '')).lower())]
            for r in matches:
                r['same_category'] = r['category'].lower() == str(request.get('category','')).lower()
                r['match_type'] = 'exact_product' if r['product_name'].lower() == str(request.get('product_name','')).lower() else 'same_vendor_related' if r['vendor_name'].lower() == str(request.get('vendor_name','')).lower() else 'same_category_alternative'
            return matches
        return self.call('catalog_lookup', (request.get('category'), request.get('vendor_name'), request.get('product_name')), run)

    def vendor(self, name):
        def run():
            registry = next((r for r in clean_records(db.load_vendors()) if r['vendor_name'].lower() == str(name).lower()), None)
            history = [p for p in clean_records(db.load_purchase_history()) if p['vendor_name'].lower() == str(name).lower()]
            try:
                api = get_vendor_risk(str(name), timeout_seconds=2)
                error = None
            except Exception as exc:
                api, error = None, type(exc).__name__
            return {'registry': registry, 'api': api, 'api_error': error, 'history': history}
        return self.call('vendor_risk_lookup', name, run)

    def policy(self):
        def run():
            text = db.load_policy_text()
            ref = re.search(r'evaluation reference date:\*\* (\d{4}-\d{2}-\d{2})', text)
            if not ref:
                raise ValueError('Policy reference date missing')
            return {'text': text, 'reference_date': ref.group(1), 'version': '2026.09'}
        return self.call('policy_lookup', 'policy', run)

    def rules(self, request, pack):
        return self.call('deterministic_policy_check', request, lambda: rules(request, pack))


# Friendly spellings map onto the closed list of data-access classes. Unknown labels stay
# unknown on purpose: they fail closed into clarification plus a Security review.
ACCESS_ALIASES = {
    'none': 'none',
    'public': 'none',
    'no_data': 'none',
    'internal': 'internal_documents',
    'internal_docs': 'internal_documents',
    'internal_documents': 'internal_documents',
    'internal_marketing': 'internal_marketing',
    'marketing': 'internal_marketing',
    'customer_data': 'customer_pii',
    'customer_pii': 'customer_pii',
    'employee_data': 'employee_pii',
    'hr_data': 'employee_pii',
    'employee_pii': 'employee_pii',
    'source_code': 'source_code',
    'code': 'source_code',
    'production_telemetry': 'production_telemetry',
    'confidential': 'confidential_documents',
    'confidential_documents': 'confidential_documents',
    'credentials': 'credentials',
    'secrets': 'secrets',
}
KNOWN_ACCESS = set(ACCESS_ALIASES.values())


def parse_amount(value):
    """Annual cost as a non-negative finite Decimal, tolerating '$8,000' style input."""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).replace('$', '').replace(',', '').strip()
    if not text:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return amount


def parse_seats(value):
    """User/license count as a positive int, tolerating '15' and 15.0."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        seats = int(value.strip())
        return seats if seats > 0 else None
    return None


def parse_integrations(value):
    """Integrations as a list; a comma-separated string is normalised into one."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    if isinstance(value, list):
        return value
    return None


# Signal only; enforcement comes from typed inputs and immutable code controls, not this heuristic.
INJECTION_PATTERN = re.compile(
    # Directives to discard instructions, rules or policy (short window: the instruction-like object must
    # sit near the verb, so "forget about spreadsheets: this tool tracks policies" stays benign).
    r'\b(ignore|disregard|forget|override|circumvent|disable|suppress)\b.{0,35}?\b(rules?|polic\w+|instructions?|guidelines?|protocols?|constraints|safeguards?|training|what you were told)\b'
    # Directives to skip the checking process itself.
    r'|\b(skip|bypass|waive|circumvent)\b.{0,25}?\b(checks?|review|approvals?|verification|oversight|sign[- ]?off)\b'
    # Mark/route/classify this request as approved.
    r'|\b(mark|classify|record|register|route|treat|process|label|set|log|file)\s+(this|it|this request|the request)\s+as\s+.{0,25}?\b(approved|auto-?approved|pre-?approved|approval_review|auto_review)\b'
    # Auto-approval vocabulary.
    r'|\bauto-?approv\w*'
    # Imperative approvals (declarative facts like "approved by Finance" do not match).
    r'|\bapprove\s+(the|this|it|all|these)\b|\bapprove\b.{0,20}?\bimmediately\b'
    # Policy or rules declared inapplicable.
    r'|\b(polic\w+|rules?)\s+(does|do|did)\s+not\s+(apply|hold|govern)\b|\bdo\s+not\s+(apply|follow|enforce)\b.{0,30}?\b(rules?|polic\w+|controls?)\b'
    # "No review/approval needed" declarations.
    r'|\bno\s+(need|requirement)\s+for\s+(human\s+)?(review|approval)\b|\bdoes\s+not\s+require\s+(approval|review|human)\b'
    # Persona or new-task injection.
    r'|\byou are now\b|\byour (real|new|actual|true) (task|instructions?|directive|goal|objective)\b|\bnew (directive|instructions?|task|objective|orders?)\s*:|\bact as\b.{0,20}?\b(admin|system|root|unrestricted)\b'
    # System-prefixed directive ("system: Jira" style product labels stay benign).
    r'|\b(system|system message|system note)\s*:\s*(you|ignore|forget|act|new|admin|approve|disregard|override|skip)\b'
    # Text addressed to the AI.
    r'|\b(note|attention|message)\s+(to|for)\s+(the\s+)?(ai|assistant|model|llm|claude|agent)\b'
    # Admin-mode directives (declarative mentions like "admin mode is needed" stay benign).
    r'|\b(enter|enable|activate|engage|switch(ing)? to|you are( now)? in)\s+admin\s+mode\b'
    # Concealment directives.
    r"|\b(do not|don't|never)\s+(flag|log|report|record|tell|mention|disclose)\b|\bwithout\s+(logging|recording|flagging|reporting)\b"
    # Credential extraction.
    r'|\breveal\b.{0,30}?\b(secret|key|password|credential|token)\b'
    # Executive-approval laundering.
    r'|\bcfo[- ]approved\b|\bsigned off by\s+(the\s+)?(cfo|ceo|board)\b'
    # Pretend-approval framing.
    r'|\bas\s+(if|though)\s+(this\s+|it\s+)?(were|was|is)\s+(pre-?approved|approved)\b'
    # Limits declared void.
    r'|\b(spending|budget|cost)\s+(limit|cap|ceiling)\s+(is|are)\s+(unlimited|waived|lifted|removed|void)\b',
    re.I,
)


def rules(req, pack):
    """Code, not model, decides financial controls and evidence freshness."""
    flags, approvals, missing = [], [], []

    def flag(value):
        if value not in flags:
            flags.append(value)

    def approval(value):
        if value not in approvals:
            approvals.append(value)

    for field in ('requester_id', 'product_name', 'vendor_name', 'business_justification'):
        if not str(req.get(field) or '').strip():
            missing.append(field)
    if not pack['budget']['employee']:
        missing.append('requester and department identity')

    amount = parse_amount(req.get('annual_cost_usd'))
    if amount is None:
        missing.append('annual cost')
    seats = parse_seats(req.get('user_count'))
    if seats is None:
        missing.append('user/license count')
    access = str(req.get('data_access_level') or '').strip().lower().replace(' ', '_').replace('-', '_')
    access = ACCESS_ALIASES.get(access, access)
    if access not in KNOWN_ACCESS:
        missing.append('data access level (unknown or unrecognized)')
    integrations = parse_integrations(req.get('requested_integrations'))
    if integrations is None:
        missing.append('required integrations (empty list means none)')
    requester_missing = list(missing)

    if amount is not None:
        approvals += (['Manager'] if amount <= 1000 else ['Department Head', 'Procurement'] if amount <= 10000 else
                      ['Department Head', 'Finance', 'Procurement'] if amount <= 25000 else ['Department Head', 'Finance', 'CFO', 'Procurement'])
        budget = pack['budget']['budget']
        try:
            available = Decimal(str(budget['available_usd'])) if budget else None
            if available is not None and (not available.is_finite() or available < 0):
                raise InvalidOperation
            if available is not None and amount > available:
                flag('budget_insufficient')
                approval('Finance')
        except (InvalidOperation, KeyError, TypeError):
            missing.append('available department budget unreadable')
            approval('Finance')
    # A missing budget row is a data problem for a human reviewer, not the requester's omission.
    if pack['budget']['employee'] and not pack['budget']['budget']:
        missing.append('department budget record not found')
        flag('budget_unverified')
        approval('Finance')
    if pack['catalog']:
        flag('existing_tool_overlap')
    v = pack['vendor']
    reg, api = v['registry'], v['api']
    if api is None:
        flag('vendor_risk_unavailable')
        missing.append('current vendor-risk API evidence')
    sensitive = any(x in access for x in ('source_code', 'production', 'cloud', 'confidential', 'pii', 'secret', 'credential'))
    sensitive |= access not in KNOWN_ACCESS
    sensitive |= any(x in str(integrations or []).lower() for x in ('production', 'cloud account', 'secret'))
    security = sensitive or api is None or reg is None
    reference_date = date.fromisoformat(pack['policy']['reference_date'])
    for record, status_key, date_key in ((reg, 'security_status', 'security_review_date'), (api, 'security_review_status', 'last_review_date')):
        if not record or str(record.get(status_key, '')).lower() != 'approved':
            security = True
        try:
            age = (reference_date - date.fromisoformat(str(record.get(date_key)))).days
            if age > 365:
                flag('vendor_review_expired')
                security = True
            if age < 0:
                flag('vendor_review_date_invalid')
                security = True
        except (ValueError, TypeError, AttributeError):
            security = True

    def normalized_status(value):
        value = str(value).lower()
        return 'approved' if value == 'approved' else 'not_completed' if value in ('pending', 'not_completed') else value

    if reg and api and (normalized_status(reg.get('security_status', '')) != normalized_status(api.get('security_review_status', '')) or
                        str(reg.get('security_review_date') or '') != str(api.get('last_review_date') or '')):
        flag('conflicting_vendor_evidence')
        security = True
    if security:
        flag('security_review_required')
        approval('Security')
    cross_region = api.get('stores_data_outside_region') if api and isinstance(api.get('stores_data_outside_region'), bool) else None
    if cross_region is None and sensitive:
        missing.append('data residency unverified')
        flag('privacy_review_required')
        approval('Privacy')
    if sensitive and any('limited' in str(r.get('status', '')).lower() for r in pack['catalog']):
        flag('restricted_use_scope')
    if 'pii' in access or cross_region:
        flag('privacy_review_required')
        approval('Privacy')
    new_vendor = not reg or str(reg.get('procurement_status', '')).lower() != 'approved'
    if (new_vendor and amount is not None and amount >= 10000) or not reg or str(reg.get('legal_terms_status', '')).lower() not in ('approved', 'standard') or cross_region:
        flag('legal_review_required')
        approval('Legal')
    raw = str(req) + str(v) + str(pack['catalog'])
    if INJECTION_PATTERN.search(raw):
        flag('prompt_injection_detected')
    if missing:
        flag('missing_information')
    return {'required_approvals': approvals, 'missing_information': missing, 'risk_flags': flags,
            'requester_missing': requester_missing, 'annual_cost_usd': str(amount) if amount is not None else None}
