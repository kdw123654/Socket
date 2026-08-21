import os
import io
import asyncio
import discord
from discord.ext import commands
import httpx
from pydub import AudioSegment
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
PRAIN_BACKEND_URL = os.getenv("PRAIN_BACKEND_URL", "http://127.0.0.1:8000/api/v1")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = discord.Bot(intents=intents)


def mix_user_audios(audio_data: dict) -> io.BytesIO:
    """
    여러 참여자의 개별 음성 트랙(WAV)을 하나의 단일 트랙으로 믹싱(Overlay)합니다.
    """
    combined: AudioSegment = None

    for user_id, audio in audio_data.items():
        audio.file.seek(0)
        track = AudioSegment.from_file(audio.file, format="wav")

        if combined is None:
            combined = track
        else:
            # 트랙 길이가 다를 경우 긴 트랙을 기준으로 오버레이 병합
            if len(track) > len(combined):
                combined = track.overlay(combined)
            else:
                combined = combined.overlay(track)

    # 믹싱된 오디오를 BytesIO 버퍼로 내보내기
    mixed_buffer = io.BytesIO()
    combined.export(mixed_buffer, format="wav")
    mixed_buffer.seek(0)
    return mixed_buffer


async def once_done(sink: discord.sinks.WaveSink, channel: discord.TextChannel, *args):
    await channel.send("🎙️ **회의 녹음이 종료되었습니다.** 모든 화자의 음성을 병합하고 AI 회의록을 생성 중입니다...")

    if not sink.audio_data:
        await channel.send("⚠️ 녹음된 음성 데이터가 없습니다.")
        return

    try:
        # [디테일 1] 모든 참여자 음성 믹싱 실행
        mixed_wav_buffer = mix_user_audios(sink.audio_data)

        # 회의 제목 생성 (예: #개발-음성-채널 회의록)
        meeting_title = f"{channel.guild.name} - #{channel.name} 회의록"

        # FastAPI 백엔드로 전송
        async with httpx.AsyncClient(timeout=180.0) as client:
            files = {
                "file": ("mixed_meeting.wav", mixed_wav_buffer, "audio/wav")
            }
            data = {
                "title": meeting_title
            }
            response = await client.post(
                f"{PRAIN_BACKEND_URL}/ai/transcribe-and-summarize",
                files=files,
                data=data
            )

        if response.status_code != 200:
            await channel.send(f"❌ 회의록 생성 실패: {response.text}")
            return

        result = response.json()
        summary_markdown = result.get("summary_markdown", "요약 내용 없음")
        note_id = result.get("id", "")

        # 디스코드 채널에 결과 Embed 전송
        embed = discord.Embed(
            title=f"📋 {result.get('title')}",
            description=summary_markdown[:4000], 
            color=discord.Color.brand_green()
        )
        embed.set_footer(text=f"Prain Note ID: {note_id} | 웹 대시보드에 자동 저장되었습니다.")
        await channel.send(embed=embed)

    except Exception as e:
        await channel.send(f"❌ 처리 중 오류 발생: {str(e)}")


@bot.event
async def on_ready():
    print(f"{bot.user} 디스코드 음성 회의 봇이 활성화되었습니다.")


@bot.slash_command(name="start_meeting", description="현재 음성 채널에 참여하여 회의 녹음을 시작합니다.")
async def start_meeting(ctx: discord.ApplicationContext):
    if not ctx.author.voice:
        await ctx.respond("❌ 먼저 음성 채널에 입장한 후 명령어를 사용해 주세요!", ephemeral=True)
        return

    vc = await ctx.author.voice.channel.connect()
    vc.start_recording(discord.sinks.WaveSink(), once_done, ctx.channel)
    await ctx.respond(f"🔴 **[{ctx.author.voice.channel.name}]** 채널에서 전원 음성 녹음을 시작합니다. (종료: `/stop_meeting`)")


@bot.slash_command(name="stop_meeting", description="회의 녹음을 중지하고 AI 회의록을 생성하여 저장합니다.")
async def stop_meeting(ctx: discord.ApplicationContext):
    if ctx.guild.voice_client:
        await ctx.respond("⏹️ 녹음을 종료합니다. 잠시만 기다려주세요...")
        ctx.guild.voice_client.stop_recording()
        await ctx.guild.voice_client.disconnect()
    else:
        await ctx.respond("❌ 봇이 현재 참여 중인 음성 채널이 없습니다.", ephemeral=True)


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)