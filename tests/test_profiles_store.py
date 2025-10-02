from pathlib import Path
from tempfile import TemporaryDirectory

from vikunja_flow.models import Profile
from vikunja_flow.profiles import ProfilesStore
from vikunja_flow.secure_store import InMemorySecretBackend


def test_save_and_load_profile():
    with TemporaryDirectory() as tmp:
        store = ProfilesStore(Path(tmp) / 'profiles.json', service_name='test-store', secret_backend=InMemorySecretBackend())
        profile = Profile(
            name='home',
            base_url='https://vik.example',
            auth_method='token',
            verify_tls=True,
            default_list_id=5,
            token='secret-token',
        )
        store.save_profile(profile, profile.token)

        loaded = store.get_profile('home')
        assert loaded.base_url == 'https://vik.example'
        assert loaded.token == 'secret-token'
        assert store.active_profile_name() == 'home'


def test_switch_active_profile():
    with TemporaryDirectory() as tmp:
        store = ProfilesStore(Path(tmp) / 'profiles.json', service_name='test-store', secret_backend=InMemorySecretBackend())
        profile_a = Profile('one', 'https://a', 'token', token='a')
        profile_b = Profile('two', 'https://b', 'token', token='b')
        store.save_profile(profile_a, profile_a.token)
        store.save_profile(profile_b, profile_b.token)

        store.set_active('two')
        assert store.active_profile_name() == 'two'
        assert store.get_profile('two').token == 'b'
