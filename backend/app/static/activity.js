import { DiscordSDK } from '@discord/embedded-app-sdk';

async function startDiscordActivity() {
  const clientId = import.meta.env.VITE_DISCORD_CLIENT_ID || window.PRAIN_CONFIG?.discordClientId;
  if (!clientId) throw new Error('Discord Application ID가 설정되지 않았습니다.');

  const discordSdk = new DiscordSDK(clientId);
  await discordSdk.ready();
  const { code } = await discordSdk.commands.authorize({
    client_id: clientId,
    response_type: 'code',
    state: '',
    prompt: 'none',
    scope: ['identify', 'guilds', 'applications.commands'],
  });
  const response = await fetch('/.proxy/api/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  });
  if (!response.ok) throw new Error('Discord 인증 토큰을 가져오지 못했습니다.');
  const { access_token } = await response.json();
  const auth = await discordSdk.commands.authenticate({ access_token });
  if (!auth?.user) throw new Error('Discord 사용자 인증에 실패했습니다.');

  document.body.classList.add('inside-discord');
  window.showPrainScreen('app');
}

if (new URLSearchParams(window.location.search).has('frame_id')) {
  startDiscordActivity().catch((error) => {
    document.body.innerHTML = `<main class="activity-error"><h1>Prain을 열 수 없어요</h1><p>${error.message}</p></main>`;
  });
}
