import argparse
from db import (get_connection, get_next_for_review, write_approved,
                set_status, get_enrichment_summary)
from constants import ENRICHMENT_FIELDS


def prompt_edit(field_name: str, current_value):
    print(f"\n  Editing {field_name} (press Enter to keep current):")
    print(f"  Current: {current_value}")
    new_value = input("  New value: ").strip()
    if not new_value:
        return current_value
    if field_name == 'tier':
        return int(new_value)
    if field_name == 'word_family':
        return [w.strip() for w in new_value.split(',')]
    return new_value


def review_session(reviewer: str):
    conn = get_connection()

    summary = get_enrichment_summary(conn)
    awaiting = summary.get('generated', 0)
    print(f"\n{awaiting} concept(s) awaiting review\n")

    reviewed = 0

    while True:
        concept = get_next_for_review(conn)
        if not concept:
            print(f"\nReview complete. {reviewed} concept(s) reviewed this session.")
            break

        print(f"\n{'='*60}")
        print(f"  CONCEPT:     {concept['term']}")
        print(f"{'='*60}")
        print(f"  Definition:  {concept['definition']}")
        print(f"  Etymology:   {concept['etymology']}")
        print(f"  Word family: {', '.join(concept['word_family'] or [])}")
        print(f"  Register:    {concept['register']}")
        print(f"  Tier:        {concept['tier']}")
        if concept['enrichment_notes']:
            print(f"  Notes:       {concept['enrichment_notes']}")
        print(f"\n  [a]pprove  [e]dit & approve  [r]eject  [s]kip  [q]uit")

        choice = input("\n  > ").strip().lower()

        if choice == 'a':
            notes = input("  Notes (optional, press Enter to skip): ").strip() or None
            fields = {k: concept[k] for k in ENRICHMENT_FIELDS}
            write_approved(conn, concept['id'], fields, notes, reviewer)
            print("  Approved")
            reviewed += 1

        elif choice == 'e':
            fields = {k: concept[k] for k in ENRICHMENT_FIELDS}
            print("\n  Which field to edit?")
            print("  [1] definition  [2] etymology  [3] word_family  "
                  "[4] register  [5] tier  [6] multiple")
            field_choice = input("  > ").strip()
            field_map = {'1': 'definition', '2': 'etymology', '3': 'word_family',
                         '4': 'register', '5': 'tier'}
            if field_choice in field_map:
                key = field_map[field_choice]
                fields[key] = prompt_edit(key, fields[key])
            elif field_choice == '6':
                for key in fields:
                    fields[key] = prompt_edit(key, fields[key])
            notes = input("\n  Reviewer notes (describe edits made): ").strip() or None
            write_approved(conn, concept['id'], fields, notes, reviewer)
            print("  Edited and approved")
            reviewed += 1

        elif choice == 'r':
            reason = input("  Reason for rejection (optional): ").strip() or None
            set_status(conn, concept['id'], 'rejected', reason)
            print("  Rejected — returned to pending queue")
            reviewed += 1

        elif choice == 's':
            print("  Skipped")

        elif choice == 'q':
            print(f"\nSession ended. {reviewed} concept(s) reviewed.")
            break

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review generated vocabulary enrichments")
    parser.add_argument('--reviewer', required=True, help="Reviewer initials or name")
    args = parser.parse_args()
    review_session(args.reviewer)
