# -*- coding: utf-8 -*-
"""What a change to one selected mapping row does to the others (FEAT-13).

The owner: "instead of having apply to selected button and separate dropdown,
it should use any selected item dropdown if one change all the select should
also change."

SELECTION ITSELF IS NOT HERE, and that is the point of the rewrite. The first
attempt hand-rolled Explorer's click rules on mouse events and got them wrong --
plain clicks accumulated instead of replacing, and ctrl-click would not take a
row back out. WPF already does this correctly with `SelectionMode="Extended"`
on a ListBox of real ListBoxItems, which is what `OneFilterParameter.pushbutton`
uses and what this dialog's own storey table has used all along. So the rows are
ListBoxItems now and WPF owns the clicking.

What is left is the one rule that belongs to cad2bim: which rows follow when a
selected row's category is changed. That is worth a test of its own, because it
is the difference between editing one layer and editing forty.
"""


def spread(rows, sender):
    """Indices whose combo should follow `sender`, given [(is_selected, combo)].

    Three rules, and each answers a way the first attempt got it wrong:

      * a change on an UNSELECTED row spreads to NOTHING. Editing one row on its
        own has to keep working exactly as it did, or the table becomes unusable
        for the single change that is most of the use;
      * the sender is never in the list. It already holds the value, and telling
        WPF to set a combo to what it is showing raises another change event;
      * only SELECTED rows follow, which is the owner's rule verbatim.

    `sender` is the combo the user touched, compared by identity: two rows can
    hold equal values and mean different layers.
    """
    owner = None
    for index, (_selected, combo) in enumerate(rows or ()):
        if combo is sender:
            owner = index
            break
    if owner is None or not rows[owner][0]:
        return []
    return [index for index, (selected, combo) in enumerate(rows)
            if selected and combo is not sender]
