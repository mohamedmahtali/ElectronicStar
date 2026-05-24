from types import SimpleNamespace

from apps.crawler.src.middlewares.captcha import CaptchaDetectionMiddleware


def _response(status=200, text=""):
    return SimpleNamespace(status=status, text=text)


def test_captcha_middleware_flags_block_statuses():
    middleware = CaptchaDetectionMiddleware()

    assert middleware._is_captcha(_response(status=403))
    assert middleware._is_captcha(_response(status=429))


def test_captcha_middleware_ignores_generic_robot_word():
    middleware = CaptchaDetectionMiddleware()

    assert not middleware._is_captcha(
        _response(text="Consultez robots.txt et les informations du site marchand.")
    )


def test_captcha_middleware_ignores_captcha_word_without_challenge_context():
    middleware = CaptchaDetectionMiddleware()

    assert not middleware._is_captcha(
        _response(text="Le script captcha peut etre charge sur la page de paiement.")
    )
    assert not middleware._is_captcha(
        _response(text="captcha robot challenge human")
    )


def test_captcha_middleware_flags_human_verification_challenge():
    middleware = CaptchaDetectionMiddleware()

    assert middleware._is_captcha(
        _response(text="Checking your browser before accessing this website.")
    )
    assert middleware._is_captcha(
        _response(text="Veuillez resoudre le captcha obligatoire pour confirmer que vous etes humain.")
    )
