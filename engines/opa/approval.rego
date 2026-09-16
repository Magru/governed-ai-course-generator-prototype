# Whose signatures publication needs, and whether the ones given are real.
#
# The same package as policy.rego, kept in its own file because it is a
# different question over different input: no brief and no course state, only a
# revision and the signatures on it.

package course.policy

import rego.v1

# Publication needs signatures. Which ones, and how many, is configuration —
# this only checks that what the organisation asked for is present. An earlier
# draft had no rule at all here, so the transition PendingApproval →
# ApprovalGranted named OPA as its layer and OPA had nothing to say about it.
allow if {
	input.action == "grant_approval"
	approval_chain_satisfied
}

approval_chain_satisfied if {
	is_array(input.signatures)
	is_number(data.org.approval.minimum_signatures)
	every role in data.org.approval.required_roles {
		some s in valid_signatures
		s.role == role
	}
	count(signers) >= data.org.approval.minimum_signatures
	count(false_signatures) == 0
}

# A signature is a person of this organisation signing in the role they hold.
# Every part is tested for being there: in Rego a missing field makes a
# comparison undefined rather than false, and `not` of undefined is true — so a
# signature with no signer at all once passed the forgery test and still filled
# its role.
valid_signature(s) if {
	is_object(s)
	is_string(s.actor)
	is_string(s.role)
	data.org.people[s.actor].role == s.role
}

valid_signatures := [s | some s in input.signatures; valid_signature(s)]

false_signatures := [s | some s in input.signatures; not valid_signature(s)]

# A signature counts once per person. Two entries by one person are one consent,
# and a chain of two that one administrator signed twice is a chain of one.
signers := {s.actor | some s in valid_signatures}

deny contains reason if {
	input.action == "grant_approval"
	signatures_malformed
	reason := {
		"rule": "approval_chain_satisfied",
		"message": "the signatures are not a list of signatures",
	}
}

deny contains reason if {
	input.action == "grant_approval"
	is_array(input.signatures)
	missing := [role |
		some role in data.org.approval.required_roles
		not role in {s.role | some s in valid_signatures}
	]
	count(missing) > 0
	reason := {
		"rule": "approval_chain_satisfied",
		"message": sprintf("publication needs a signature from %v", [missing]),
	}
}

deny contains reason if {
	input.action == "grant_approval"
	is_array(input.signatures)
	is_number(data.org.approval.minimum_signatures)
	count(signers) < data.org.approval.minimum_signatures
	reason := {
		"rule": "approval_chain_satisfied",
		"message": sprintf("%v distinct signers present, %v required", [count(signers), data.org.approval.minimum_signatures]),
	}
}

# Two clauses, because `not is_number(x)` with x absent is undefined, not true —
# the trap the brief-shaped clauses below already record.
minimum_unstated if not data.org.approval.minimum_signatures

minimum_unstated if {
	data.org.approval.minimum_signatures
	not is_number(data.org.approval.minimum_signatures)
}

signatures_malformed if not input.signatures

signatures_malformed if {
	input.signatures
	not is_array(input.signatures)
}

deny contains reason if {
	input.action == "grant_approval"
	minimum_unstated
	reason := {
		"rule": "approval_chain_satisfied",
		"message": "the organisation has not said how many signatures publication needs",
	}
}

deny contains reason if {
	input.action == "grant_approval"
	is_array(input.signatures)
	some s in false_signatures
	reason := {
		"rule": "approval_chain_satisfied",
		"message": sprintf("%v is not a signature by a person of this organisation in the role they hold", [s]),
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

