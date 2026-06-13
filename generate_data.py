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


def add_member(rows, member_id, clan_id, name, gender, birth_year, death_year, father_id, mother_id, generation_num, bio):
    rows.append([
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
    ])


def add_marriage(rows, marriage_id, clan_id, spouse_a_id, spouse_b_id, marry_year):
    if not spouse_a_id or not spouse_b_id or spouse_a_id == spouse_b_id:
        return marriage_id
    rows.append([marriage_id, clan_id, spouse_a_id, spouse_b_id, marry_year or "", ""])
    return marriage_id + 1


def make_death_year(birth_year, generation_num):
    if generation_num >= 5 and random.random() < 0.72:
        return ""
    death_year = birth_year + random.randint(58, 94)
    return death_year if death_year <= 2026 else ""


def person_name(surname, index, gender):
    pool = MALE_NAMES if gender == "M" else FEMALE_NAMES
    return surname + pool[index % len(pool)] + str(index // len(pool) + 1)


def spouse_name(index, gender):
    if gender == "F":
        return SPOUSE_SURNAMES[index % len(SPOUSE_SURNAMES)] + "氏" + str(index // len(SPOUSE_SURNAMES) + 1)
    return "外姓夫" + str(index + 1)


def generate_clan(target_size, clan_id, surname, next_member_id, next_marriage_id):
    members = []
    marriages = []
    couples_by_generation = {}
    name_index = 0
    spouse_index = clan_id * 100000
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
        add_member(members, member_id, clan_id, surname + "太公" + str(index + 1), "M", birth, make_death_year(birth, 1), "", "", 1, "第1代族谱源头")
        member_id += 1
        if len(members) >= target_size:
            break
        mother_id = member_id
        mother_birth = birth + random.randint(-4, 5)
        add_member(members, member_id, clan_id, spouse_name(spouse_index, "F"), "F", mother_birth, make_death_year(mother_birth, 1), "", "", 1, "第1代配偶")
        member_id += 1
        couples_by_generation[1].append((father_id, mother_id, birth))
        spouse_index += 1

    generation = 2
    while len(members) < target_size and generation <= 12:
        previous = couples_by_generation.get(generation - 1, [])
        if not previous:
            break
        couples_by_generation[generation] = []
        for father_id, mother_id, parent_birth in previous:
            if len(members) >= target_size:
                break
            child_count = random.randint(2, 5)
            actual_children = 0
            for _ in range(child_count):
                if len(members) >= target_size:
                    break
                gender = "M" if random.random() < 0.52 else "F"
                birth = parent_birth + random.randint(21, 35)
                child_id = member_id
                add_member(
                    members,
                    member_id,
                    clan_id,
                    person_name(surname, name_index, gender),
                    gender,
                    birth,
                    make_death_year(birth, generation),
                    father_id,
                    mother_id,
                    generation,
                    "第{}代成员，批量生成数据".format(generation),
                )
                member_id += 1
                name_index += 1
                actual_children += 1

                if len(members) >= target_size:
                    break
                if random.random() < 0.84:
                    spouse_gender = "F" if gender == "M" else "M"
                    spouse_id = member_id
                    spouse_birth = birth + random.randint(-5, 5)
                    add_member(
                        members,
                        member_id,
                        clan_id,
                        spouse_name(spouse_index, spouse_gender),
                        spouse_gender,
                        spouse_birth,
                        make_death_year(spouse_birth, generation),
                        "",
                        "",
                        generation,
                        "第{}代配偶，批量生成数据".format(generation),
                    )
                    member_id += 1
                    spouse_index += 1
                    if gender == "M":
                        couples_by_generation[generation].append((child_id, spouse_id, birth))
                    else:
                        couples_by_generation[generation].append((spouse_id, child_id, birth))
            if actual_children > 0:
                marriage_id = add_marriage(marriages, marriage_id, clan_id, father_id, mother_id, parent_birth + random.randint(18, 28))
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

    return genealogies, all_members[:total], all_marriages


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
