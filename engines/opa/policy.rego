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

within_limits if {
	input.brief.node_count <= data.org.thresholds.max_nodes_per_course
	input.brief.minutes_per_lesson <= data.org.thresholds.max_minutes_per_lesson
	count(input.brief.audience) <= data.org.thresholds.max_audience_breadth
}

state_permits if {
	input.course_state in {"AwaitingBrief", "BriefValidation", "OutlineDrafting", "ContentInProgress"}
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
	input.brief.minutes_per_lesson > data.org.thresholds.max_minutes_per_lesson
	reason := {
		"rule": "within_limits",
		"message": sprintf("%v minutes per lesson, the limit is %v", [input.brief.minutes_per_lesson, data.org.thresholds.max_minutes_per_lesson]),
	}
}

deny contains reason if {
	not input.course_state in {"AwaitingBrief", "BriefValidation", "OutlineDrafting", "ContentInProgress"}
	reason := {
		"rule": "state_permits",
		"message": sprintf("%v is not a state this action is legal in", [input.course_state]),
	}
}

deny contains reason if {
	not input.action in {"submit_brief", "generate_outline", "generate_node"}
	reason := {
		"rule": "known_action",
		"message": sprintf("%v is not an action this policy governs", [input.action]),
	}
}
