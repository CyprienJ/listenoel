from django.shortcuts import redirect
from django.urls import reverse


class EmailVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_verified:
            # List of authorised URL even if not verified
            allowed_urls = [
                reverse('profile'),
                reverse('verify_email_sent'),
                reverse('verify_email_confirm', kwargs={'uidb64': 'dummy', 'token': 'dummy'}).split('dummy')[0],
                reverse('resend_verification'),
                reverse('logout'),
                reverse('login'),
                reverse('welcome'),
                reverse('password_reset'),
                reverse('password_reset_done'),
                reverse('password_reset_confirm', kwargs={'uidb64': 'dummy', 'token': 'dummy'}).split('dummy')[0],
                reverse('password_reset_complete'),
                reverse('unsubscribe_token', kwargs={'uidb64': 'dummy', 'token': 'dummy'}).split('dummy')[0],
            ]

            if not any(request.path == url
                       or (url != reverse('welcome')
                           and request.path.startswith(url)) for url in allowed_urls):
                return redirect('verify_email_sent')

        return self.get_response(request)
