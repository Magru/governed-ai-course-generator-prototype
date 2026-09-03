# Who may take this action, over this audience, in this state.
#
# The rules live here rather than in Python because the specification gives this
# question to OPA and because a policy that is data can be reviewed, versioned
# and changed without a deployment. Thresholds are never written here — they come
# from organizational configuration, and hard-coding one would move a decision
# out of the hands of whoever owns it.

package course.policy

import rego.v1

default allow := false

allow if {
	input.action in {"submit_brief", "generate_outline", "generate_node"}
	input.actor.role in {"course-author", "training-administrator"}
	audience_permitted
	within_limits
	state_permits
}

# An author may only write for audiences they were granted.
audience_permitted if {
	every team in input.brief.audience {
		team in data.org.grants[input.actor.id].may_author_for
	}
}

# One owner per question. Lesson length and audience breadth are parts of "is
# this brief satisfiable", which belongs to Z3 — and asking both meant OPA
# refused first and terminally, so the unsat core Z3 exists to produce could
# never be reached.
within_limits if {
	input.brief.node_count <= data.org.thresholds.max_nodes_per_course
}

# Only generation is gated on state here. Which states an action is legal in is
# the transition table's question, and an earlier version of this file answered
# it too — refusing BriefSubmitted from BlockedRecoverable, a recovery path the
# table guarantees. A policy refusal is terminal, so that turned a recoverable
# stop into the end of the revision.
state_permits if {
	input.action != "generate_node"
}

state_permits if {
	input.action == "generate_node"
	input.course_state == "ContentInProgress"
}

# Publication needs signatures. Which ones, and how many, is configuration —
# this only checks that what the organisation asked for is present. An earlier
# draft had no rule at all here, so the transition PendingApproval →
# ApprovalGranted named OPA as its layer and OPA had nothing to say about it.
allow if {
	input.action == "grant_approval"
	approval_chain_satisfied
}

approval_chain_satisfied if {
	every role in data.org.approval.required_roles {
		some signature in input.signatures
		signature.role == role
	}
	count(input.signatures) >= data.org.approval.minimum_signatures
}

deny contains reason if {
	input.action == "grant_approval"
	missing := [role |
		some role in data.org.approval.required_roles
		not role in {s.role | some s in input.signatures}
	]
	count(missing) > 0
	reason := {
		"rule": "approval_chain_satisfied",
		"message": sprintf("publication needs a signature from %v", [missing]),
	}
}

deny contains reason if {
	input.action == "grant_approval"
	count(input.signatures) < data.org.approval.minimum_signatures
	reason := {
		"rule": "approval_chain_satisfied",
		"message": sprintf("%v signatures present, %v required", [count(input.signatures), data.org.approval.minimum_signatures]),
	}
}

# Silence about the approval rule is not consent to publish.
deny contains reason if {
	input.action == "grant_approval"
	not data.org.approval.required_roles
	reason := {
		"rule": "approval_chain_satisfied",
		"message": "the organisation has not said whose signatures publication needs",
	}
}

# Refusing with the rule that denied and a sentence a person can act on. A bare
# `allow = false` would tell an author nothing about what to change.
deny contains reason if {
	not audience_permitted
	ungranted := [team |
		some team in input.brief.audience
		not team in data.org.grants[input.actor.id].may_author_for
	]
	reason := {
		"rule": "audience_permitted",
		"message": sprintf("%v may not author for %v", [input.actor.id, ungranted]),
	}
}

deny contains reason if {
	input.brief.node_count > data.org.thresholds.max_nodes_per_course
	reason := {
		"rule": "within_limits",
		"message": sprintf("%v nodes requested, the limit is %v", [input.brief.node_count, data.org.thresholds.max_nodes_per_course]),
	}
}

deny contains reason if {
	input.action == "generate_node"
	input.course_state != "ContentInProgress"
	reason := {
		"rule": "state_permits",
		"message": sprintf("a node cannot be generated while the revision is %v", [input.course_state]),
	}
}

# Every way of failing needs its own reason, or `allow` is false with nothing in
# `deny` and the caller has to invent one. A refusal a Python function wrote is
# not a refusal the policy engine made.
deny contains reason if {
	input.action in {"submit_brief", "generate_outline", "generate_node"}
	not input.actor.role in {"course-author", "training-administrator"}
	reason := {
		"rule": "known_role",
		"message": sprintf("%v is not a role that may author", [input.actor.role]),
	}
}

# `not is_number(input.brief.node_count)` looks right and is not: with the key
# absent the inner call is undefined, and the negation of an undefined expression
# is undefined too — so the clause never fired and the refusal had no reason.
# Testing the reference itself is the idiom that holds.
# Both of these are about a brief, so both are gated on there being one. Without
# the gate they fired on an approval — which carries no brief — and a revision
# short of a signature was refused for not saying how many nodes it wanted.
deny contains reason if {
	input.action in {"submit_brief", "generate_outline", "generate_node"}
	not input.brief.node_count
	reason := {
		"rule": "within_limits",
		"message": "the brief does not say how many nodes it asks for",
	}
}

deny contains reason if {
	input.action in {"submit_brief", "generate_outline", "generate_node"}
	not data.org.thresholds.max_nodes_per_course
	reason := {
		"rule": "within_limits",
		"message": "the organisation's node limit is not configured",
	}
}

deny contains reason if {
	not input.action in {"submit_brief", "generate_outline", "generate_node", "grant_approval"}
	reason := {
		"rule": "known_action",
		"message": sprintf("%v is not an action this policy governs", [input.action]),
	}
}
