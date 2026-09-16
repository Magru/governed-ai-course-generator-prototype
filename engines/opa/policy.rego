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

AUTHORING := {"submit_brief", "generate_outline", "generate_node"}

# What a person does to a course once it exists, and who may. Signing off a
# node is an author's act as much as an administrator's; what reaches or leaves
# learners is the administrator's alone.
PERSON_ACTS := {
	"approve_node": {"course-author", "training-administrator"},
	"publish_revision": {"training-administrator"},
	"withdraw_revision": {"training-administrator"},
	"archive_revision": {"training-administrator"},
	"notify_learners": {"training-administrator"},
}

# Taken by the system on its own behalf, never by a person: admitting screened
# content, moving the live pointer, reading sources for a prompt.
SYSTEM_ACTS := {"admit_to_revision", "move_live_pointer", "retrieve_sources"}

KNOWN := ((AUTHORING | {name | some name, _ in PERSON_ACTS}) | SYSTEM_ACTS) | {"grant_approval"}

allow if {
	some roles
	roles = PERSON_ACTS[input.action]
	input.actor.kind == "person"
	input.actor.role in roles
	audience_permitted
}

allow if {
	input.action in SYSTEM_ACTS
	input.actor.kind == "system"
}

deny contains reason if {
	some roles
	roles = PERSON_ACTS[input.action]
	input.actor.kind == "person"
	not input.actor.role in roles
	reason := {
		"rule": "known_role",
		"message": sprintf("%v may not %v; it needs one of %v", [input.actor.id, input.action, roles]),
	}
}

deny contains reason if {
	PERSON_ACTS[input.action]
	not input.actor.kind == "person"
	reason := {
		"rule": "person_only",
		"message": sprintf("%v is a person's act; %v is not a person", [input.action, input.actor.id]),
	}
}

deny contains reason if {
	input.action in SYSTEM_ACTS
	not input.actor.kind == "system"
	reason := {
		"rule": "system_only",
		"message": sprintf("%v is taken by the system on its own behalf, not by %v", [input.action, input.actor.id]),
	}
}

allow if {
	input.action in {"submit_brief", "generate_outline", "generate_node"}
	input.actor.role in {"course-author", "training-administrator"}
	audience_permitted
	within_limits
	state_permits
}

# An author may only write for audiences they were granted.
audience_permitted if {
	count(input.brief.audience) > 0
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

# Refusing with the rule that denied and a sentence a person can act on. A bare
# `allow = false` would tell an author nothing about what to change.
# Asked of whoever authors, and of a person acting on a course. A system asked
# to take a person's act is refused for that, not for having no audience.
audience_question if input.action in AUTHORING

audience_question if {
	PERSON_ACTS[input.action]
	input.actor.kind == "person"
}

deny contains reason if {
	audience_question
	not audience_permitted
	# object.get, not a path: for someone the organisation never granted, the
	# path is undefined, `team in undefined` is undefined, and the list came
	# out empty — a refusal that named no team.
	granted := object.get(data.org.grants, [input.actor.id, "may_author_for"], [])
	ungranted := [team | some team in input.brief.audience; not team in granted]
	count(ungranted) > 0
	reason := {
		"rule": "audience_permitted",
		"message": sprintf("%v may not author for %v", [input.actor.id, ungranted]),
	}
}

# A refusal that names nothing sends a person looking for nothing. A course for
# no one, or an author the organisation has granted nothing, is said as such.
audience_empty if not input.brief.audience

audience_empty if count(input.brief.audience) == 0

deny contains reason if {
	audience_question
	audience_empty
	reason := {
		"rule": "audience_permitted",
		"message": "the course names no audience, and a course for no one cannot be authored",
	}
}

deny contains reason if {
	input.action in AUTHORING
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
	not input.action in KNOWN
	reason := {
		"rule": "known_action",
		"message": sprintf("%v is not an action this policy governs", [input.action]),
	}
}
