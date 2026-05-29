"""
Анализ качества сгенерированных заявок на курсы повышения квалификации.

Вход:  applications.csv
Выход: cities.png, specialities.png, report.md
"""

import sys
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def load(path: str) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8")


def plot_bar(series: pd.Series, title: str, out: str):
    series.value_counts().plot(kind="bar", edgecolor="white")
    plt.title(title)
    plt.ylabel("Число заявок")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    plt.close()


def write_report(df: pd.DataFrame, out: str):
    n = len(df)
    lines = [f"# Отчёт по {n} заявкам\n"]

    for col, label, threshold in [
        ("city", "Города", 40),
        ("speciality", "Специальности", 35),
    ]:
        counts = df[col].value_counts()
        top_pct = counts.iloc[0] / n * 100
        lines.append(f"## {label}\n")
        lines.append(f"- Уникальных: {len(counts)}")
        lines.append(f"- Топ-1: {counts.index[0]} — {counts.iloc[0]} ({top_pct:.0f}%)")
        if top_pct > threshold:
            lines.append(f"- Превышен порог {threshold}% — mode collapse")
        lines.append("")

    lines.append("## Желаемые курсы\n")
    for course, cnt in df["desired_course"].value_counts().items():
        lines.append(f"- {course}: {cnt} ({cnt/n*100:.0f}%)")
    lines.append("")

    lines.append("## Кросс-таблица город x специальность\n")
    ct = pd.crosstab(df["city"], df["speciality"])
    lines.append("```")
    lines.append(ct.to_string())
    lines.append("```\n")

    lines.append("## Числовые поля\n")
    for col in ["age", "years_of_experience", "graduation_year"]:
        s = df[col]
        lines.append(f"- {col}: min={s.min()}, max={s.max()}, mean={s.mean():.1f}")

    Path(out).write_text("\n".join(lines), encoding="utf-8")


def main(path: str = "applications.csv"):
    df = load(path)
    plot_bar(df["city"],       "Распределение по городам",       "cities.png")
    plot_bar(df["speciality"], "Распределение по специальностям", "specialities.png")
    write_report(df, "report.md")
    print("Готово: cities.png, specialities.png, report.md")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "applications.csv"
    main(path)