% Coverage, and the same search asked to keep what it found on the way.
%
% Datalog says what reaches what. This answers the harder question — what is
% missing, and why — and it is asked one course at a time, never swept.

% A node covers an objective only once a person has approved it. Teaching it is
% not the same as it counting: an unapproved node is work, not coverage.
covers(Node, Objective) :-
    approved(Node),
    teaches(Node, Skill),
    develops(Skill, Objective).

uncovered(Course, Objective) :-
    requires(Course, Objective),
    \+ ( contains(Course, Node), covers(Node, Objective) ).

% The explanation is not a second implementation. It is the same search, keeping
% the partial matches it passed over — which is what turns "not covered" into
% "you have a node that teaches this, and nobody has approved it yet".
why_uncovered(Course, Objective, explanation(Objective, Skills, Partial, Reason)) :-
    uncovered(Course, Objective),
    findall(S, develops(S, Objective), Skills),
    findall(N-S, ( contains(Course, N), teaches(N, S), member(S, Skills) ), Partial),
    reason(Partial, Reason).

reason([], no_node_teaches_it).
reason([_|_], taught_but_not_approved).
