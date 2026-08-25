import unittest
from market_sources import parse_results, parse_market_codes, source_base, result_url

SAMPLE = """
<select id='pool-name'>
<option data-name='SRILANKA POOL' data-code='p7952'>SRILANKA POOL</option>
<option data-name='TAIWAN POOL' data-code='p8294'>TAIWAN POOL</option>
</select>
<table><thead><tr><th>Periode</th><th>Tanggal</th><th>Nomor</th></tr></thead>
<tbody>
<tr><td>2116</td><td>2026-08-17 14:11:41</td><td class='nomor-history'>2659</td></tr>
<tr><td>2115</td><td>2026-08-16 14:11:21</td><td class='nomor-history'>8951</td></tr>
</tbody></table>
"""

SAMPLE_WITH_DAY = """
<table><thead><tr><th>Periode</th><th>Hari</th><th>Tanggal</th><th>Nomor</th></tr></thead>
<tbody><tr><td>2116</td><td>Senin</td><td>2026-08-17 14:11:41</td><td>2659</td></tr></tbody></table>
"""

class ParserTests(unittest.TestCase):
    def test_results(self):
        rows = parse_results(SAMPLE)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].period, '2116')
        self.assertEqual(rows[0].number, '2659')
        self.assertIsNotNone(rows[0].parsed_at)

    def test_results_with_hari_column(self):
        rows = parse_results(SAMPLE_WITH_DAY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].date_text, '2026-08-17 14:11:41')
        self.assertEqual(rows[0].number, '2659')

    def test_codes(self):
        m = parse_market_codes(SAMPLE)
        self.assertEqual(m['SRILANKA POOL'], 'p7952')
        self.assertEqual(m['TAIWAN POOL'], 'p8294')

    def test_url(self):
        self.assertEqual(source_base('https://x.test/history/number'), 'https://x.test')
        self.assertEqual(result_url('https://x.test/history/number', '/history/result/{code}/kosong', 'p7952'), 'https://x.test/history/result/p7952/kosong')

if __name__ == '__main__':
    unittest.main()
