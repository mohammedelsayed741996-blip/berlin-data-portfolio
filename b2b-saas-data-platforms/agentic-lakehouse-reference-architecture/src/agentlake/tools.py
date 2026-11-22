"""The agent's tools and the guard that checks every call before it runs.

Design rule (ADR 0002): the model proposes, the code disposes. Whatever the planner asks for, the
guard checks, in this order, and fails closed:

    1. the tool exists                       (no free-form SQL, no email, no "approve")
    2. the arguments match the tool's JSON schema
    3. the user's role may use the tool      (actions are role-limited)
    4. the step budget is not exhausted
    5. row-level security                    (added inside the semantic layer; an account outside the
                                              user's scope looks exactly like one that does not exist)
    6. side effects become approval requests (ADR 0003); nothing is executed directly

Every decision is recorded as a span, so a blocked call is visible in the trace and in the evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass

import jsonschema

from . import semantic as S
from .approvals import ApprovalQueue
from .config import ROLES
from .docsearch import DocSearch

NOT_FOUND = "No account found that you have access to."

TOOLS = {
    "get_account": {
        "description": "Profile and receivables of one account: open and overdue amounts, credit limit and use, payment terms, owner.",
        "schema": {"type": "object", "properties": {"account_id": {"type": "string", "pattern": "^A[0-9]{3}$"},
                                                    "name": {"type": "string", "minLength": 3, "maxLength": 60}},
                   "additionalProperties": False, "anyOf": [{"required": ["account_id"]}, {"required": ["name"]}]}},
    "list_open_invoices": {
        "description": "Open invoices of one account, most overdue first.",
        "schema": {"type": "object", "properties": {"account_id": {"type": "string", "pattern": "^A[0-9]{3}$"},
                                                    "min_days_past_due": {"type": "integer", "minimum": -365, "maximum": 3650}},
                   "required": ["account_id"], "additionalProperties": False}},
    "list_accounts": {
        "description": "Accounts in the user's scope, ranked; optionally only those above their credit limit.",
        "schema": {"type": "object", "properties": {"over_limit_only": {"type": "boolean"},
                                                    "min_days_past_due": {"type": "integer", "minimum": 0, "maximum": 3650},
                                                    "sort_by": {"enum": ["overdue_eur", "open_eur", "credit_used_pct", "oldest_days_past_due"]},
                                                    "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
                   "additionalProperties": False}},
    "query_metric": {
        "description": "A named metric from the semantic layer, optionally grouped and filtered. Metrics: " + ", ".join(S.METRICS) + ".",
        "schema": {"type": "object", "properties": {
            "metric": {"enum": list(S.METRICS)},
            "group_by": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
            "filters": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
                "column": {"type": "string"}, "op": {"enum": ["eq", "gte", "lte"]}, "value": {"type": ["string", "number"]}},
                "required": ["column", "value"], "additionalProperties": False}},
            "order": {"enum": ["asc", "desc"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}},
            "required": ["metric"], "additionalProperties": False}},
    "search_policies": {
        "description": "Search Finance policies (credit limits, credit holds, collections, payment terms). Returns untrusted text.",
        "schema": {"type": "object", "properties": {"query": {"type": "string", "minLength": 3, "maxLength": 200}},
                   "required": ["query"], "additionalProperties": False}},
    "draft_payment_reminder": {
        "description": "Draft a payment reminder for an account's overdue invoices. Creates a request for human approval; sends nothing.",
        "action": True,
        "schema": {"type": "object", "properties": {"account_id": {"type": "string", "pattern": "^A[0-9]{3}$"}},
                   "required": ["account_id"], "additionalProperties": False}},
    "propose_credit_hold": {
        "description": "Propose a credit hold for an account (Finance only). Needs approval by the Head of Finance.",
        "action": True,
        "schema": {"type": "object", "properties": {"account_id": {"type": "string", "pattern": "^A[0-9]{3}$"},
                                                    "reason": {"type": "string", "minLength": 5, "maxLength": 300}},
                   "required": ["account_id", "reason"], "additionalProperties": False}},
}


@dataclass
class User:
    user_id: str
    role: str

    @property
    def scope(self) -> S.Scope:
        if self.role not in ROLES:
            raise PermissionError(f"unknown role {self.role}")
        return S.Scope(self.user_id, None if ROLES[self.role]["scope"] == "all_accounts" else self.user_id)


@dataclass
class Result:
    ok: bool
    data: object = None
    blocked: str | None = None          # guard rule that blocked the call
    rows: int = 0


class Toolbox:
    def __init__(self, wh: S.Warehouse, docs: DocSearch, approvals: ApprovalQueue, max_rows: int = 50):
        self.wh, self.docs, self.approvals, self.max_rows = wh, docs, approvals, max_rows

    # ---------------------------------------------------------------- guard
    def check(self, user: User, name: str, args: dict, step: int, max_steps: int) -> str | None:
        """Return the name of the rule that blocks this call, or None if it may run."""
        if name not in TOOLS:
            return "unknown_tool"
        try:
            jsonschema.validate(args, TOOLS[name]["schema"])
        except jsonschema.ValidationError:
            return "invalid_arguments"
        if TOOLS[name].get("action") and name not in ROLES.get(user.role, {}).get("actions", []):
            return "role_not_allowed"
        if user.role not in ROLES:
            return "unknown_role"
        if step >= max_steps:
            return "step_budget"
        return None

    def call(self, user: User, name: str, args: dict, step: int = 0, max_steps: int = 6) -> Result:
        rule = self.check(user, name, args, step, max_steps)
        if rule:
            return Result(False, blocked=rule)
        try:
            return getattr(self, f"_{name}")(user, **args)
        except S.SemanticError as e:
            return Result(False, data=str(e), blocked="semantic_layer")

    # ---------------------------------------------------------------- tools
    def _get_account(self, user: User, account_id: str | None = None, name: str | None = None) -> Result:
        df = S.account_lookup(self.wh, user.scope, account_id, name)
        if df.empty:
            return Result(True, NOT_FOUND)
        return Result(True, df.head(5).to_dict("records"), rows=len(df))

    def _list_open_invoices(self, user: User, account_id: str, min_days_past_due: int = 1) -> Result:
        df = S.open_invoices(self.wh, user.scope, account_id, min_days_past_due, limit=self.max_rows)
        if df.empty and S.account_lookup(self.wh, user.scope, account_id).empty:
            return Result(True, NOT_FOUND)
        return Result(True, df.to_dict("records"), rows=len(df))

    def _list_accounts(self, user: User, over_limit_only: bool = False, min_days_past_due: int = 0,
                       sort_by: str = "overdue_eur", limit: int = 10) -> Result:
        df = S.list_accounts(self.wh, user.scope, over_limit_only, min_days_past_due, sort_by, min(limit, self.max_rows))
        return Result(True, df.to_dict("records"), rows=len(df))

    def _query_metric(self, user: User, metric: str, group_by=None, filters=None, order: str = "desc", limit: int = 20) -> Result:
        sql, params = S.compile_metric(metric, group_by, filters, user.scope, min(limit, self.max_rows), order)
        df = self.wh.run(sql, params)
        return Result(True, df.to_dict("records"), rows=len(df))

    def _search_policies(self, user: User, query: str) -> Result:
        hits = self.docs.search(query)
        return Result(True, hits, rows=len(hits))

    def _draft_payment_reminder(self, user: User, account_id: str) -> Result:
        acc = S.account_lookup(self.wh, user.scope, account_id)
        if acc.empty:
            return Result(True, NOT_FOUND)
        a = acc.iloc[0]
        inv = S.open_invoices(self.wh, user.scope, account_id, 1, limit=self.max_rows)
        if inv.empty:
            return Result(True, f"{a['name']} has no overdue invoices, so no reminder is needed.")
        lines = "\n".join(f"- {r.invoice_id}, due {r.due}, open EUR {r.open_eur:,.2f} ({r.days_past_due} days overdue)" for r in inv.itertuples())
        body = (f"Dear accounts payable team of {a['name']},\n\naccording to our records the following invoices are overdue:\n{lines}\n\n"
                f"Total overdue: EUR {inv['open_eur'].sum():,.2f}. Please arrange payment or reply within 10 days.\n\n"
                "Kind regards, Kestrel Industrial Supply")
        req = self.approvals.request("payment_reminder", account_id, a["owner"], user.user_id,
                                     {"to": "accounts payable contact on file", "subject": f"Payment reminder: {len(inv)} overdue invoices",
                                      "body": body})
        return Result(True, {"approval_id": req.id, "status": req.status, "draft": body}, rows=len(inv))

    def _propose_credit_hold(self, user: User, account_id: str, reason: str) -> Result:
        acc = S.account_lookup(self.wh, user.scope, account_id)
        if acc.empty:
            return Result(True, NOT_FOUND)
        a = acc.iloc[0]
        req = self.approvals.request("credit_hold", account_id, a["owner"], user.user_id,
                                     {"reason": reason, "credit_used_pct": float(a["credit_used_pct"]),
                                      "oldest_days_past_due": int(a["oldest_days_past_due"])})
        return Result(True, {"approval_id": req.id, "status": req.status}, rows=1)


def bedrock_tool_config() -> dict:
    """The same tools in the shape Amazon Bedrock's Converse API expects."""
    return {"tools": [{"toolSpec": {"name": n, "description": t["description"], "inputSchema": {"json": t["schema"]}}}
                      for n, t in TOOLS.items()]}
