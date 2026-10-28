# ruff: noqa: E501

"""HTML adapter: a sudact.ru document page becomes a SudactDocument.

Fixtures mimic the real layout (left column, banners, service blocks after the
act) so junk never leaks into the act text.
"""

import unittest

from src.infrastructure.sudact_html import parse_sudact_page

PAGE = """<html><head><title>Приговор № 1-120/2026 от 14 апреля 2026 г. по делу № 1-120/2026 :: СудАкт.ру</title>
<meta property="og:author" content="Новочебоксарский городской суд (Чувашская Республика )">
<meta property="og:url" content="https://sudact.ru/regular/doc/abc/">
</head><body>
<table><tr>
<td class="h-col2-rightmenu"><div class="h-col2_print"><a href="/regular/doc/print/abc/">печатать</a></div></td>
<td class="h-col1 h-col1-inner3">
<div class="bookmarkBlockContainer"><div class="bookmarkIcon" title="Добавить избранное"></div></div>
<h1>Приговор № 1-120/2026 от 14 апреля 2026 г. по делу № 1-120/2026</h1>
<div class="b-justice"><a href="/regular/court/x/">Новочебоксарский городской суд (Чувашская Республика ) </a> - Уголовное </div>
<div class="sudact-top-banner"><a href="/away/b2/"><img src="/static/i/banner.jpg" alt="реклама"/></a></div>
<hr class="hr-h1">
Дело № 1-120/2026<br ><br >УИД 21RS0022-01-2026-000904-27<br ><br >
<b >П Р И Г О В О Р</b><br >Именем Российской Федерации<br >
г. Новочебоксарск<br >У С Т А Н О В И Л:<br >подсудимый совершил кражу по ст. 158 ч. 2 УК РФ.<br >
П Р И Г О В О Р И Л:<br >признать виновным по ст. 158 ч. 2 УК РФ.<br >
Председательствующий П.А. Кудашкин
<script>window.Ya.adfoxCode.createAdaptive({containerId: "adfox_1"});</script>
<div id="adfox_176946271353223789"></div>
<h3>Суд:</h3>Новочебоксарский городской суд (Чувашская Республика ) <a href="/regular/court/x/">(подробнее)</a><br>
<h3> Судьи дела:</h3>Кудашкин Павел Александрович (судья)
<div class="h-col1-spacer"></div>
<div class="footer_adv adv_inside_text"><div id="adfox_2"></div></div>
</td>
</tr></table></body></html>"""

PAGE_NO_HR = PAGE.replace('<hr class="hr-h1">', "")
PAGE_NO_META = PAGE.replace(
    '<meta property="og:author" content="Новочебоксарский городской суд (Чувашская Республика )">',
    "",
)


class ParseSudactPageTests(unittest.TestCase):
    def test_full_page_fields(self):
        doc = parse_sudact_page(
            "https://sudact.ru/regular/doc/abc/", PAGE.encode(), "2026-10-28T01:02:03+00:00"
        )
        self.assertEqual(
            doc.title, "Приговор № 1-120/2026 от 14 апреля 2026 г. по делу № 1-120/2026"
        )
        self.assertEqual(doc.act_kind, "приговор")
        self.assertTrue(doc.is_verdict)
        self.assertEqual(doc.case_number, "1-120/2026")
        self.assertEqual(doc.uid, "21RS0022-01-2026-000904-27")
        self.assertEqual(doc.decision_date, "2026-04-14")
        self.assertEqual(doc.court_name, "Новочебоксарский городской суд")
        self.assertEqual(doc.region, "Чувашская Республика")
        self.assertEqual(doc.fetched_at, "2026-10-28T01:02:03+00:00")
        self.assertEqual(doc.html_sha256, __import__("hashlib").sha256(PAGE.encode()).hexdigest())
        self.assertEqual(
            doc.text_sha256, __import__("hashlib").sha256(doc.text.encode()).hexdigest()
        )

    def test_act_text_is_clean_and_complete(self):
        doc = parse_sudact_page("https://sudact.ru/regular/doc/abc/", PAGE.encode())
        self.assertIn("УИД 21RS0022-01-2026-000904-27", doc.text)
        self.assertIn("У С Т А Н О В И Л:", doc.text)
        self.assertIn("П Р И Г О В О Р И Л:", doc.text)
        self.assertIn("Председательствующий П.А. Кудашкин", doc.text)
        # neither service blocks, nor banners, nor ad scripts leak into the text
        self.assertNotIn("Судьи дела", doc.text)
        self.assertNotIn("adfox", doc.text)
        self.assertNotIn("window.Ya", doc.text)
        self.assertNotIn("печатать", doc.text)
        self.assertNotIn("реклама", doc.text)

    def test_fallback_without_hr_takes_whole_column(self):
        doc = parse_sudact_page("u", PAGE_NO_HR.encode())
        self.assertIn("УИД 21RS0022-01-2026-000904-27", doc.text)
        # the service block is still cut off at the first <h3>
        self.assertNotIn("Судьи дела", doc.text)

    def test_court_from_b_justice_without_meta(self):
        doc = parse_sudact_page("u", PAGE_NO_META.encode())
        self.assertEqual(doc.court_name, "Новочебоксарский городской суд")
        self.assertEqual(doc.region, "Чувашская Республика")

    def test_title_tag_used_without_h1(self):
        no_h1 = PAGE.replace(
            "<h1>Приговор № 1-120/2026 от 14 апреля 2026 г. по делу № 1-120/2026</h1>", ""
        )
        doc = parse_sudact_page("u", no_h1.encode())
        self.assertEqual(
            doc.title, "Приговор № 1-120/2026 от 14 апреля 2026 г. по делу № 1-120/2026"
        )
        self.assertEqual(doc.act_kind, "приговор")


if __name__ == "__main__":
    unittest.main()
