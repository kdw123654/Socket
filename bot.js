import 'dotenv/config';
import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  Client,
  Events,
  GatewayIntentBits,
  REST,
  Routes,
  SlashCommandBuilder,
} from 'discord.js';

const token = process.env.DISCORD_BOT_TOKEN;
const clientId = process.env.DISCORD_CLIENT_ID;
if (!token || !clientId) {
  throw new Error('DISCORD_BOT_TOKEN과 DISCORD_CLIENT_ID를 .env에 설정해 주세요.');
}

const commands = [
  new SlashCommandBuilder().setName('prain').setDescription('Prain 프로젝트 메뉴를 엽니다.'),
  new SlashCommandBuilder().setName('프로젝트요약').setDescription('현재 프로젝트 요약을 확인합니다.'),
].map((command) => command.toJSON());

const rest = new REST({ version: '10' }).setToken(token);
await rest.put(Routes.applicationCommands(clientId), { body: commands });

const client = new Client({ intents: [GatewayIntentBits.Guilds] });

client.once(Events.ClientReady, (readyClient) => {
  console.log(`Prain bot logged in as ${readyClient.user.tag}`);
});

client.on(Events.InteractionCreate, async (interaction) => {
  if (!interaction.isChatInputCommand()) return;

  if (interaction.commandName === '프로젝트요약') {
    await interaction.reply({
      content: '**Prain 플랫폼 진행도 62%**\n• Discord 연결 완료\n• GitHub 연동 준비 중\n• API 이슈 1건 확인 필요',
      ephemeral: true,
    });
    return;
  }

  const activityUrl = process.env.PRAIN_APP_URL;
  const components = activityUrl
    ? [new ActionRowBuilder().addComponents(
        new ButtonBuilder().setLabel('Prain 대시보드 열기').setStyle(ButtonStyle.Link).setURL(activityUrl),
      )]
    : [];
  await interaction.reply({
    content: 'Prain이 연결되었습니다. `/프로젝트요약`으로 현재 진행 상황을 확인하세요.',
    components,
    ephemeral: true,
  });
});

await client.login(token);
