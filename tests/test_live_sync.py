import unittest

from entrust.live_sync import BrowserWorker


class FakePage:
    def __init__(self, url, goto_url=None):
        self.url = url
        self.goto_url = goto_url

    def is_closed(self):
        return False

    def goto(self, _url, **_kwargs):
        if self.goto_url:
            self.url = self.goto_url


class FakeContext:
    def __init__(self, pages):
        self.pages = pages

    def cookies(self):
        return []


class BrowserWorkerLoginTest(unittest.TestCase):
    def test_uses_logged_in_page_instead_of_original_login_page(self):
        worker = BrowserWorker()
        login_page = FakePage("https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx")
        main_page = FakePage("https://eztrade.entrust.com.tw/hnsweb/default.aspx")

        selected = worker._update_login_state(FakeContext([login_page, main_page]), login_page)

        self.assertIs(selected, main_page)
        self.assertTrue(worker.status()["logged_in"])
        self.assertEqual(worker.status()["current_url"], main_page.url)

    def test_does_not_treat_certificate_popup_as_logged_in(self):
        worker = BrowserWorker()
        login_page = FakePage("https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx")
        popup = FakePage("https://eztrade.entrust.com.tw/hnsweb/TransPage.aspx")

        selected = worker._update_login_state(FakeContext([login_page, popup]), login_page)

        self.assertIs(selected, login_page)
        self.assertFalse(worker.status()["logged_in"])

    def test_reopens_main_page_to_reuse_shared_session(self):
        worker = BrowserWorker()
        login_page = FakePage(
            "https://eztrade.entrust.com.tw/hnsweb/loginnew.aspx",
            goto_url="https://eztrade.entrust.com.tw/hnsweb/default.aspx",
        )
        context = FakeContext([login_page])

        selected = worker._ensure_authenticated(context, login_page)

        self.assertIs(selected, login_page)
        self.assertTrue(worker.status()["logged_in"])

    def test_treats_standalone_accounting_page_as_logged_in(self):
        worker = BrowserWorker()
        accounting_page = FakePage("https://eztrade.entrust.com.tw/hnsweb/TS0106.aspx?drpSum=1")

        selected = worker._update_login_state(FakeContext([accounting_page]), accounting_page)

        self.assertIs(selected, accounting_page)
        self.assertTrue(worker.status()["logged_in"])


if __name__ == "__main__":
    unittest.main()
