# 8. Pipeline sous-titres automatiques (Whisper)

1. Convertir l'audio en WAV 16 kHz : `npx remotion ffmpeg -i video.mp4 -ar 16000 audio.wav`.
2. Installer Whisper et un modèle, puis transcrire avec horodatage par mot :

```ts
import {installWhisperCpp, downloadWhisperModel, transcribe, toCaptions} from '@remotion/install-whisper-cpp';

await installWhisperCpp({to: whisperPath, version: '1.5.5'});
await downloadWhisperModel({model: 'medium.en', folder: whisperPath});
const output = await transcribe({
  inputPath: 'audio.wav', whisperPath, model: 'medium.en', tokenLevelTimestamps: true,
});
const {captions} = toCaptions({whisperCppOutput: output});
```

3. Regrouper en pages avec `createTikTokStyleCaptions`, puis afficher avec le composant de la section 4.
4. Importer ou exporter des fichiers `.srt` avec `parseSrt` et `serializeSrt`.
5. Variante cloud : `openAiWhisperApiToCaptions` convertit la réponse de l'API OpenAI Whisper.
