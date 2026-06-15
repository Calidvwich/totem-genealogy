import csv
import os
import random
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
MEMBERS_OUTPUT = APP_DIR / "members_load.csv"
MARRIAGES_OUTPUT = APP_DIR / "marriages_load.csv"
GENEALOGIES_OUTPUT = APP_DIR / "genealogies_load.csv"

DEFAULT_TOTAL = int(os.getenv("GENEALOGY_MEMBER_COUNT", "105000"))
RANDOM_SEED = int(os.getenv("GENEALOGY_RANDOM_SEED", "20260613"))

SURNAMES = ["张", "李", "王", "陈", "刘", "赵", "黄", "周", "吴", "徐"]
MALE_NAMES = ["伯仁", "仲义", "明德", "远山", "承志", "启文", "修远", "景行", "怀瑾", "彦祖", "思齐", "文博", "弘毅", "嘉树", "云帆", "知远"]
FEMALE_NAMES = ["婉清", "明珠", "远晴", "若兰", "静姝", "雅文", "思宁", "月华", "嘉仪", "安然", "佩玉", "清妍", "书瑶", "雨桐", "若溪", "语嫣"]
SPOUSE_SURNAMES = ["李", "王", "陈", "刘", "赵", "黄", "周", "吴", "徐", "孙", "胡", "朱", "林", "郭", "何", "罗"]


def parse_total():
    if len(sys.argv) > 1:
        return int(sys.argv[1])
    return DEFAULT_TOTAL


def clan_sizes(total):
    first = 60000
    if total < 10:
        return [total]
    remaining = max(0, total - first)
    if remaining == 0:
        return [total] + [0] * 9
    base = remaining // 9
    extra = remaining % 9
    sizes = [first]
    for index in range(9):
        sizes.append(base + (1 if index < extra else 0))
    return sizes


def add_member(rows, people, member_id, clan_id, name, gender, birth_year, death_year, father_id, mother_id, generation_num, bio):
    row = [
        member_id,
        clan_id,
        name,
        gender,
        birth_year or "",
        death_year or "",
        father_id or "",
        mother_id or "",
        generation_num,
        bio,
    ]
    rows.append(row)
    people[member_id] = {
        "member_id": member_id,
        "clan_id": clan_id,
        "name": name,
        "gender": gender,
        "birth_year": birth_year,
        "death_year": death_year or "",
        "father_id": father_id or "",
        "mother_id": mother_id or "",
        "generation_num": generation_num,
    }


def interval_end(year):
    return year or 9999


def has_marriage_overlap(existing, person_id, start_year, end_year):
    for old_start, old_end in existing.get(person_id, []):
        if start_year < interval_end(old_end) and interval_end(end_year) > old_start:
            return True
    return False


def add_marriage(rows, marriage_periods, marriage_id, clan_id, spouse_a_id, spouse_b_id, marry_year, divorce_year=""):
    if not spouse_a_id or not spouse_b_id or spouse_a_id == spouse_b_id:
        return marriage_id
    if has_marriage_overlap(marriage_periods, spouse_a_id, marry_year, divorce_year):
        return marriage_id
    if has_marriage_overlap(marriage_periods, spouse_b_id, marry_year, divorce_year):
        return marriage_id
    rows.append([marriage_id, clan_id, spouse_a_id, spouse_b_id, marry_year or "", divorce_year or ""])
    marriage_periods.setdefault(spouse_a_id, []).append((marry_year, divorce_year or ""))
    marriage_periods.setdefault(spouse_b_id, []).append((marry_year, divorce_year or ""))
    return marriage_id + 1


def make_couple(father_id, mother_id, father_birth, mother_birth, father_death="", mother_death=""):
    death_limit = min([year for year in (father_death, mother_death) if year] or [9999])
    marry_min = max(father_birth, mother_birth) + 18
    marry_max = min(max(father_birth, mother_birth) + 30, death_limit - 2)
    if marry_max < marry_min:
        marry_year = marry_min
    else:
        marry_year = random.randint(marry_min, marry_max)

    divorce_year = ""
    if death_limit > marry_year + 8 and random.random() < 0.12:
        divorce_min = marry_year + 4
        divorce_max = min(marry_year + 34, death_limit - 1)
        if divorce_max >= divorce_min:
            divorce_year = random.randint(divorce_min, divorce_max)

    return {
        "father_id": father_id,
        "mother_id": mother_id,
        "father_birth": father_birth,
        "mother_birth": mother_birth,
        "father_death": father_death or "",
        "mother_death": mother_death or "",
        "marry_year": marry_year,
        "divorce_year": divorce_year,
    }


def child_birth_year(couple):
    lower = max(couple["father_birth"], couple["mother_birth"], couple["marry_year"]) + 1
    upper = lower + random.randint(2, 16)
    if couple["divorce_year"]:
        upper = min(upper, couple["divorce_year"] - 1)
    parent_deaths = [year for year in (couple["father_death"], couple["mother_death"]) if year]
    if parent_deaths:
        upper = min(upper, min(parent_deaths) - 1)
    if upper < lower:
        return None
    return random.randint(lower, upper)


def make_death_year(birth_year, generation_num):
    if generation_num >= 5 and random.random() < 0.72:
        return ""
    death_year = birth_year + random.randint(58, 94)
    return death_year if death_year <= 2026 else ""


def next_member_name(surname, generation_num, generation_counters):
    generation_counters[generation_num] = generation_counters.get(generation_num, 0) + 1
    return "{}_{}_{}".format(surname, generation_num, generation_counters[generation_num])


def generate_clan(target_size, clan_id, surname, next_member_id, next_marriage_id):
    members = []
    marriages = []
    people = {}
    marriage_periods = {}
    couples_by_generation = {}
    generation_counters = {}
    member_id = next_member_id
    marriage_id = next_marriage_id

    if target_size <= 0:
        return members, marriages, member_id, marriage_id

    root_couples = max(6, min(72, target_size // 900))
    couples_by_generation[1] = []
    for index in range(root_couples):
        if len(members) >= target_size:
            break
        birth = 1838 + index % 18
        father_id = member_id
        father_death = make_death_year(birth, 1)
        add_member(members, people, member_id, clan_id, next_member_name(surname, 1, generation_counters), "M", birth, father_death, "", "", 1, "第1代族谱源头")
        member_id += 1
        if len(members) >= target_size:
            break
        mother_id = member_id
        mother_birth = birth + random.randint(-4, 5)
        mother_death = make_death_year(mother_birth, 1)
        add_member(members, people, member_id, clan_id, next_member_name(surname, 1, generation_counters), "F", mother_birth, mother_death, "", "", 1, "第1代配偶")
        member_id += 1
        couples_by_generation[1].append(make_couple(father_id, mother_id, birth, mother_birth, father_death, mother_death))

    generation = 2
    while len(members) < target_size and generation <= 12:
        previous = couples_by_generation.get(generation - 1, [])
        if not previous:
            break
        couples_by_generation[generation] = []
        for couple in previous:
            if len(members) >= target_size:
                break
            child_count = random.randint(2, 5)
            actual_children = 0
            max_child_birth = ""
            for _ in range(child_count):
                if len(members) >= target_size:
                    break
                gender = "M" if random.random() < 0.52 else "F"
                birth = child_birth_year(couple)
                if birth is None:
                    continue
                child_id = member_id
                child_death = make_death_year(birth, generation)
                add_member(
                    members,
                    people,
                    member_id,
                    clan_id,
                    next_member_name(surname, generation, generation_counters),
                    gender,
                    birth,
                    child_death,
                    couple["father_id"],
                    couple["mother_id"],
                    generation,
                    "第{}代成员，批量生成数据".format(generation),
                )
                member_id += 1
                actual_children += 1
                max_child_birth = max(max_child_birth or birth, birth)

                if len(members) >= target_size:
                    break
                if random.random() < 0.84:
                    spouse_gender = "F" if gender == "M" else "M"
                    spouse_id = member_id
                    spouse_birth = birth + random.randint(-5, 5)
                    spouse_death = make_death_year(spouse_birth, generation)
                    add_member(
                        members,
                        people,
                        member_id,
                        clan_id,
                        next_member_name(surname, generation, generation_counters),
                        spouse_gender,
                        spouse_birth,
                        spouse_death,
                        "",
                        "",
                        generation,
                        "第{}代配偶，批量生成数据".format(generation),
                    )
                    member_id += 1
                    if gender == "M":
                        couples_by_generation[generation].append(make_couple(child_id, spouse_id, birth, spouse_birth, child_death, spouse_death))
                    else:
                        couples_by_generation[generation].append(make_couple(spouse_id, child_id, spouse_birth, birth, spouse_death, child_death))
            if actual_children > 0:
                divorce_year = couple["divorce_year"]
                if divorce_year and max_child_birth and divorce_year <= max_child_birth:
                    divorce_year = ""
                marriage_id = add_marriage(
                    marriages,
                    marriage_periods,
                    marriage_id,
                    clan_id,
                    couple["father_id"],
                    couple["mother_id"],
                    couple["marry_year"],
                    divorce_year,
                )
        generation += 1

    return members[:target_size], marriages, member_id, marriage_id


def generate_all(total):
    random.seed(RANDOM_SEED)
    sizes = clan_sizes(total)
    genealogies = []
    all_members = []
    all_marriages = []
    next_member_id = 1
    next_marriage_id = 1

    for clan_index, size in enumerate(sizes, start=1):
        surname = SURNAMES[(clan_index - 1) % len(SURNAMES)]
        genealogies.append([clan_index, "{}氏族谱".format(surname), surname, 1])
        members, marriages, next_member_id, next_marriage_id = generate_clan(
            size,
            clan_index,
            surname,
            next_member_id,
            next_marriage_id,
        )
        all_members.extend(members)
        all_marriages.extend(marriages)

    all_members = all_members[:total]
    validate_generated_data(all_members, all_marriages)
    return genealogies, all_members, all_marriages


def to_int(value):
    if value == "" or value is None:
        return None
    return int(value)


def validate_generated_data(members, marriages):
    people = {
        int(row[0]): {
            "clan_id": int(row[1]),
            "name": row[2],
            "gender": row[3],
            "birth_year": to_int(row[4]),
            "death_year": to_int(row[5]),
            "father_id": to_int(row[6]),
            "mother_id": to_int(row[7]),
            "generation_num": to_int(row[8]),
        }
        for row in members
    }
    marriage_by_pair = {}
    intervals = {}
    for row in marriages:
        marriage_id = int(row[0])
        father_id = int(row[2])
        mother_id = int(row[3])
        marry_year = to_int(row[4])
        divorce_year = to_int(row[5])
        father = people.get(father_id)
        mother = people.get(mother_id)
        if not father or not mother:
            raise ValueError("marriage {} references missing member".format(marriage_id))
        if father["gender"] != "M" or mother["gender"] != "F":
            raise ValueError("marriage {} must be male-female father/mother order".format(marriage_id))
        if father["birth_year"] >= marry_year or mother["birth_year"] >= marry_year:
            raise ValueError("marriage {} violates parent birth < marry year".format(marriage_id))
        for person_id in (father_id, mother_id):
            for old_start, old_end in intervals.get(person_id, []):
                if marry_year < interval_end(old_end) and interval_end(divorce_year) > old_start:
                    raise ValueError("member {} has overlapping marriages".format(person_id))
            intervals.setdefault(person_id, []).append((marry_year, divorce_year))
        if divorce_year and divorce_year <= marry_year:
            raise ValueError("marriage {} violates marry < divorce".format(marriage_id))
        if father["death_year"] and divorce_year and divorce_year >= father["death_year"]:
            raise ValueError("marriage {} violates divorce < father death".format(marriage_id))
        if mother["death_year"] and divorce_year and divorce_year >= mother["death_year"]:
            raise ValueError("marriage {} violates divorce < mother death".format(marriage_id))
        if father["death_year"] and marry_year >= father["death_year"]:
            raise ValueError("marriage {} violates marry < father death".format(marriage_id))
        if mother["death_year"] and marry_year >= mother["death_year"]:
            raise ValueError("marriage {} violates marry < mother death".format(marriage_id))
        marriage_by_pair[(father_id, mother_id)] = {
            "marry_year": marry_year,
            "divorce_year": divorce_year,
        }

    for member_id, child in people.items():
        father_id = child["father_id"]
        mother_id = child["mother_id"]
        if not father_id and not mother_id:
            continue
        father = people.get(father_id)
        mother = people.get(mother_id)
        if not father or not mother:
            raise ValueError("child {} references missing parent".format(member_id))
        if father["gender"] != "M":
            raise ValueError("child {} father must be male".format(member_id))
        if mother["gender"] != "F":
            raise ValueError("child {} mother must be female".format(member_id))
        marriage = marriage_by_pair.get((father_id, mother_id))
        if not marriage:
            raise ValueError("child {} parents must have a marriage".format(member_id))
        birth_year = child["birth_year"]
        if not (father["birth_year"] < marriage["marry_year"] < birth_year):
            raise ValueError("child {} violates parent birth < marry < child birth".format(member_id))
        if mother["birth_year"] >= marriage["marry_year"]:
            raise ValueError("child {} violates mother birth < marry".format(member_id))
        if marriage["divorce_year"] and birth_year >= marriage["divorce_year"]:
            raise ValueError("child {} violates child birth < divorce".format(member_id))
        if father["death_year"] and birth_year >= father["death_year"]:
            raise ValueError("child {} violates child birth < father death".format(member_id))
        if mother["death_year"] and birth_year >= mother["death_year"]:
            raise ValueError("child {} violates child birth < mother death".format(member_id))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def main():
    total = parse_total()
    genealogies, members, marriages = generate_all(total)
    write_csv(GENEALOGIES_OUTPUT, genealogies)
    write_csv(MEMBERS_OUTPUT, members)
    write_csv(MARRIAGES_OUTPUT, marriages)
    print("generated {} genealogies -> {}".format(len(genealogies), GENEALOGIES_OUTPUT))
    print("generated {} members -> {}".format(len(members), MEMBERS_OUTPUT))
    print("generated {} marriages -> {}".format(len(marriages), MARRIAGES_OUTPUT))


if __name__ == "__main__":
    main()
