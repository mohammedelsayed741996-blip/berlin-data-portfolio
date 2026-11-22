"""Human approval for every action with side effects (ADR 0003).

The agent can only create a pending request. A person decides, through the API, and the rules
for who may decide are enforced here: account managers approve their own reminders, Finance
approves any reminder, and a credit hold needs the Head of Finance and a different person from
the one who proposed it (four-eyes principle). Nothing is ever sent by this demo; an approved
request is where an email or ERP integration would pick it up.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field

APPROVERS = {"payment_reminder": {"account_manager", "finance"}, "credit_hold": {"head_of_finance"}}


@dataclass
class Approval:
    id: int
    kind: str
    account_id: str
    owner: str
    requested_by: str
    payload: dict
    status: str = "pending"
    decided_by: str | None = None
    decided_at: float | None = None
    created_at: float = field(default_factory=time.time)


class ApprovalError(PermissionError):
    pass


class ApprovalQueue:
    def __init__(self):
        self.items: dict[int, Approval] = {}
        self._ids = itertools.count(1)

    def request(self, kind: str, account_id: str, owner: str, requested_by: str, payload: dict) -> Approval:
        a = Approval(next(self._ids), kind, account_id, owner, requested_by, payload)
        self.items[a.id] = a
        return a

    def decide(self, approval_id: int, user: str, role: str, approve: bool) -> Approval:
        a = self.items.get(approval_id)
        if a is None:
            raise ApprovalError("no such request")
        if a.status != "pending":
            raise ApprovalError(f"request already {a.status}")
        if role not in APPROVERS[a.kind]:
            raise ApprovalError(f"role {role} cannot decide on {a.kind}")
        if role == "account_manager" and user != a.owner:
            raise ApprovalError("account managers can only approve requests for their own accounts")
        if a.kind == "credit_hold" and user == a.requested_by:
            raise ApprovalError("four-eyes principle: the person who proposed a credit hold cannot approve it")
        a.status, a.decided_by, a.decided_at = ("approved" if approve else "rejected"), user, time.time()
        return a

    def pending(self, user: str, role: str) -> list[Approval]:
        return [a for a in self.items.values() if a.status == "pending" and role in APPROVERS[a.kind]
                and (role != "account_manager" or a.owner == user)]
