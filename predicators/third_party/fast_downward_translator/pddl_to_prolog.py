#! /usr/bin/env python3
import logging
import itertools

import predicators.third_party.fast_downward_translator.normalize as normalize
import predicators.third_party.fast_downward_translator.pddl as pddl
import predicators.third_party.fast_downward_translator.timers as timers


class PrologProgram:

    def __init__(self):
        self.facts = []
        self.rules = []
        self.objects = set()

        def predicate_name_generator():
            for count in itertools.count():
                yield "p$%d" % count

        self.new_name = predicate_name_generator()

    def add_fact(self, atom):
        self.facts.append(Fact(atom))
        self.objects |= set(atom.args)

    def add_rule(self, rule):
        self.rules.append(rule)

    def dump(self, file=None):
        for fact in self.facts:
            logging.info(fact, file=file)
        for rule in self.rules:
            logging.info(getattr(rule, "type", "none"), rule, file=file)

    def normalize(self):
        # Normalized prolog programs have the following properties:
        # 1. Each variable that occurs in the effect of a rule also occurs in its
        #    condition.
        # 2. The variables that appear in each effect or condition are distinct.
        # 3. There are no rules with empty condition.
        self.remove_free_effect_variables()
        self.split_duplicate_arguments()
        self.convert_trivial_rules()

    def split_rules(self):
        import predicators.third_party.fast_downward_translator.split_rules as split_rules

        # Splits rules whose conditions can be partitioned in such a way that
        # the parts have disjoint variable sets, then split n-ary joins into
        # a number of binary joins, introducing new pseudo-predicates for the
        # intermediate values.
        new_rules = []
        for rule in self.rules:
            new_rules += split_rules.split_rule(rule, self.new_name)
        self.rules = new_rules

    def remove_free_effect_variables(self):
        """Remove free effect variables like the variable Y in the rule p(X, Y)

        :- q(X). This is done by introducing a new predicate.

        @object, setting it true for all objects, and translating the above
        rule to p(X, Y) :- q(X), @object(Y).
        After calling this, no new objects should be introduced!
        """

        # Note: This should never be necessary for typed domains.
        # Leaving it in at the moment regardless.
        must_add_predicate = False
        for rule in self.rules:
            eff_vars = get_variables([rule.effect])
            cond_vars = get_variables(rule.conditions)
            if not eff_vars.issubset(cond_vars):
                must_add_predicate = True
                eff_vars -= cond_vars
                for var in sorted(eff_vars):
                    rule.add_condition(pddl.Atom("@object", [var]))
        if must_add_predicate:
            logging.info("Unbound effect variables: Adding @object predicate.")
            self.facts += [
                Fact(pddl.Atom("@object", [obj])) for obj in self.objects
            ]

    def split_duplicate_arguments(self):
        """Make sure that no variable occurs twice within the same symbolic
        fact, like the variable X does in p(X, Y, X).

        This is done by renaming the second and following occurrences of
        the variable and adding equality conditions. For example p(X, Y,
        X) is translated to p(X, Y, X@0) with the additional condition
        =(X, X@0); the equality predicate must be appropriately
        instantiated somewhere else.
        """
        printed_message = False
        for rule in self.rules:
            if rule.rename_duplicate_variables() and not printed_message:
                logging.info("Duplicate arguments: Adding equality conditions.")
                printed_message = True

    def convert_trivial_rules(self):
        """Convert rules with an empty condition into facts.

        This must be called after bounding rule effects, so that rules
        with an empty condition must necessarily have a variable-free
        effect. Variable-free effects are the only ones for which a
        distinction between ground and symbolic atoms is not necessary.
        """
        must_delete_rules = []
        for i, rule in enumerate(self.rules):
            if not rule.conditions:
                assert not get_variables([rule.effect])
                self.add_fact(
                    pddl.Atom(rule.effect.predicate, rule.effect.args))
                must_delete_rules.append(i)
        if must_delete_rules:
            logging.info("Trivial rules: Converted to facts.")
            for rule_no in must_delete_rules[::-1]:
                del self.rules[rule_no]


def get_variables(symbolic_atoms):
    variables = set()
    for sym_atom in symbolic_atoms:
        variables |= {arg for arg in sym_atom.args if arg[0] == "?"}
    return variables


class Fact:

    def __init__(self, atom):
        self.atom = atom

    def __str__(self):
        return "%s." % self.atom


class Rule:

    def __init__(self, conditions, effect):
        self.conditions = conditions
        self.effect = effect

    def add_condition(self, condition):
        self.conditions.append(condition)

    def get_variables(self):
        return get_variables(self.conditions + [self.effect])

    def _rename_duplicate_variables(self, atom, new_conditions):
        used_variables = set()
        for i, var_name in enumerate(atom.args):
            if var_name[0] == "?":
                if var_name in used_variables:
                    new_var_name = "%s@%d" % (var_name, len(new_conditions))
                    atom = atom.replace_argument(i, new_var_name)
                    new_conditions.append(
                        pddl.Atom("=", [var_name, new_var_name]))
                else:
                    used_variables.add(var_name)
        return atom

    def rename_duplicate_variables(self):
        extra_conditions = []
        self.effect = self._rename_duplicate_variables(self.effect,
                                                       extra_conditions)
        old_conditions = self.conditions
        self.conditions = []
        for condition in old_conditions:
            self.conditions.append(
                self._rename_duplicate_variables(condition, extra_conditions))
        self.conditions += extra_conditions
        return bool(extra_conditions)

    def __str__(self):
        cond_str = ", ".join(map(str, self.conditions))
        return "%s :- %s." % (self.effect, cond_str)


def translate_typed_object(prog, obj, type_dict):
    supertypes = type_dict[obj.type_name].supertype_names
    for type_name in [obj.type_name] + supertypes:
        prog.add_fact(pddl.TypedObject(obj.name, type_name).get_atom())


def translate_facts(prog, task):
    type_dict = {type.name: type for type in task.types}
    for obj in task.objects:
        translate_typed_object(prog, obj, type_dict)
    for fact in task.init:
        assert isinstance(fact, pddl.Atom) or isinstance(fact, pddl.Assign)
        if isinstance(fact, pddl.Atom):
            prog.add_fact(fact)


def translate(task):
    # Note: The function requires that the task has been normalized.
    with timers.timing("Generating Datalog program"):
        prog = PrologProgram()
        translate_facts(prog, task)
        for conditions, effect in normalize.build_exploration_rules(task):
            prog.add_rule(Rule(conditions, effect))
    with timers.timing("Normalizing Datalog program", block=True):
        # Using block=True because normalization can output some messages
        # in rare cases.
        prog.normalize()
        prog.split_rules()
    return prog
