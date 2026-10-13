# AOSP Android 12 no navegador — laboratório remoto

Este repositório contém o **scaffold de execução remota**, não uma imagem Android já compilada. O frontend é um painel de controlo; o ecrã é transmitido pelo noVNC a partir de uma janela real do Android Emulator a executar no servidor. Não há páginas HTML que imitem as Definições, o launcher ou outras aplicações Android.

> **Estado honesto desta entrega:** os ficheiros de frontend/backend/configuração foram criados e podem ser verificados localmente. Não foi possível compilar o AOSP, iniciar o Android Emulator nem testar o boot neste ambiente de criação: aqui não existe uma máquina AOSP construída, `/dev/kvm` nem um servidor Android persistente. Os critérios de aceitação relativos a arranque, versão nas Definições e interação real só podem ser marcados após executar este projeto num host Linux com a imagem criada pelo script abaixo. A pasta `aosp-image/` está deliberadamente vazia até esse passo.

## Versão AOSP fixada

- **Android:** 12.0.0 (Snow Cone), versão da plataforma Release 40.
- **Tag do manifesto:** `android-platform-12.0.0_r40`.
- **Build ID do manifesto:** `12861604`.
- **Produto:** `sdk_phone_x86_64-userdebug`.
- **Imagem esperada:** artefactos AVD produzidos pelo build oficial do AOSP — kernel do emulador, ramdisk, `system.img` e restantes partições presentes no diretório do produto.

Referência verificável: [manifesto oficial Android Platform 12.0.0 Release 40](https://android.googlesource.com/platform/manifest/+/refs/tags/android-platform-12.0.0_r40). O AOSP publica instruções para compilar e executar imagens AVD próprias em [Use Android Emulator virtual devices](https://source.android.com/docs/setup/test/avd), e instruções gerais em [Download the Android source](https://source.android.com/docs/setup/download) e [Build Android](https://source.android.com/docs/setup/build/building).

Foi escolhida uma tag oficial de manutenção 12.0.0 em vez do primeiro release `android-12.0.0_r1`, para partir de uma revisão posterior da mesma versão principal. Não é uma ROM de um fabricante e não inclui Google Play Services proprietário; as aplicações disponíveis são as que forem construídas na imagem AOSP.

## Arquitetura

```text
Navegador do utilizador
  └── HTTPS (Caddy/reverse proxy recomendado)
      └── gateway Nginx + autenticação HTTP Basic
          ├── /             painel web estático
          ├── /api/*        FastAPI → adb → Android Emulator
          ├── /vnc.html     cliente noVNC
          └── /websockify   WebSocket → VNC
                              └── Xvfb + Openbox + x11vnc
                                  └── Android Emulator
                                      └── imagem AOSP 12 x86-64
```

### Componentes incluídos

- `frontend/`: painel web, estado do sistema, controlos para iniciar/parar/reiniciar e comandos ADB para navegação, energia e notificações. Não implementa uma interface Android falsa.
- `server/app.py`: serviço FastAPI que lança o Android Emulator, consulta `getprop`/estado de boot através de ADB e encaminha eventos de tecla, toque e deslize.
- `server/Dockerfile`: ambiente Linux com Android SDK command-line tools, Android Emulator, Xvfb, x11vnc e websockify/noVNC.
- `gateway/`: Nginx com autenticação obrigatória e encaminhamento do HTTP/WebSocket.
- `docker-compose.yml`: rede privada entre serviços, persistência de dados Android e acesso a `/dev/kvm`.
- `scripts/build-aosp-android12.sh`: fixa o checkout à tag AOSP, sincroniza os repositórios, compila o produto AVD e copia os artefactos para `aosp-image/`.

## 1. Requisitos do servidor

Utilize um host Linux x86-64 com virtualização KVM disponível, Docker Engine e Docker Compose v2. O dispositivo final só precisará de um navegador moderno; não tem de instalar SDK, emulador ou aplicações.

A compilação AOSP é pesada. A documentação oficial recomenda pelo menos **64 GB de RAM** e cerca de **400 GB de espaço livre** para checkout e build. Consulte [os requisitos oficiais de desenvolvimento AOSP](https://source.android.com/docs/setup/start/requirements). O servidor de execução deve disponibilizar `/dev/kvm`; sem aceleração de hardware, a emulação pode tornar-se demasiado lenta ou não arrancar com esta configuração.

Instale no host de compilação os pacotes exigidos pela versão AOSP e o comando `repo`, seguindo a documentação oficial. Faça a compilação num host dedicado ou num volume persistente com espaço suficiente.

## 2. Compilar o Android 12 AOSP verdadeiro

Clone este projeto no servidor e obtenha uma checkout AOSP separada. Por exemplo:

```bash
mkdir -p ~/src/aosp-android12
cd ~/src/aosp-android12
# Instale previamente o launcher repo segundo a documentação oficial.
```

A partir da raiz da checkout AOSP, execute o script incluído no projeto. Ajuste o caminho para o clone do projeto:

```bash
AOSP_SRC_DIR="$PWD" \
DEPLOY_IMAGE_DIR="$HOME/android12-browser-lab/aosp-image" \
bash "$HOME/android12-browser-lab/scripts/build-aosp-android12.sh"
```

O script executa `repo init` para a tag `android-platform-12.0.0_r40`, `repo sync`, `lunch sdk_phone_x86_64-userdebug` e `make`. Não considera a compilação bem-sucedida se não encontrar pelo menos `system.img`, `ramdisk.img` e um kernel no diretório de saída. Copia os artefactos do produto para `aosp-image/`; a imagem não é reconstituída a partir de HTML nem substituída por uma aplicação simulada.

Se a versão/tag do AOSP sofrer incompatibilidades com o ambiente de build do host, siga os avisos da documentação AOSP dessa tag e corrija o ambiente de compilação. Não altere para uma imagem Android de terceiros se o objetivo continuar a ser provar a origem AOSP.

## 3. Configurar credenciais e arrancar os serviços

A partir da pasta do projeto:

```bash
cp .env.example .env
```

Edite `.env` e defina um nome de utilizador e uma palavra-passe longa, aleatória e exclusiva (pelo menos 16 caracteres). Depois:

```bash
docker compose up --build -d
docker compose logs -f android
```

A construção da imagem Docker transfere as ferramentas oficiais do Android SDK. A imagem de sistema a executar, pelo contrário, vem da checkout AOSP compilada e montada em `aosp-image/`.

Por omissão, o gateway publica a porta `8080` **apenas em `127.0.0.1`**, para não expor HTTP sem cifragem na Internet. Abra localmente para diagnóstico em `http://127.0.0.1:8080` ou avance para a publicação HTTPS abaixo. A autenticação HTTP Basic é aplicada tanto ao painel como ao stream VNC e à API.

Os dados persistentes do dispositivo são guardados no volume Docker `android-data`. `Reiniciar Android` envia `adb reboot`; `Reiniciar emulador` termina e volta a iniciar o processo do emulador sem apagar intencionalmente os dados; `Parar` pára apenas o processo do emulador.

### Publicar num domínio HTTPS

Aponte o DNS de um domínio para o servidor e instale/configure Caddy no host. Exemplo de `Caddyfile`:

```caddy
android.exemplo.pt {
    reverse_proxy 127.0.0.1:8080
}
```

Recarregue o Caddy e aceda a `https://android.exemplo.pt`. Caddy gere o certificado TLS automaticamente se os requisitos de DNS/portas públicas estiverem cumpridos. Mantenha a porta 8080 ligada apenas a loopback e não publique as portas internas do serviço Android, VNC ou ADB. Use firewall, atualizações de segurança e credenciais fortes.

## 4. Verificações depois do arranque

A API de diagnóstico, atrás da mesma autenticação, é `/api/status`. Verifique todos os pontos seguintes no host efetivamente implantado:

1. `image_ready` é `true` e `image_files` confirma os ficheiros esperados.
2. `emulator_process_running` é `true`.
3. `android_state` muda para `booted`.
4. `android_version` responde `12` e o `android_sdk` deve corresponder à API 31.
5. No ecrã transmitido, abra **Definições → Acerca do telefone** (ou o ecrã equivalente dessa imagem) e confirme a versão/build no Android original.
6. Abra aplicações efetivamente incluídas na imagem AOSP e teste toque, teclado, deslize, voltar, Home e notificações.
7. Reinicie Android e emulador e confirme que os dados que espera persistir continuam presentes.

O estado mostrado no painel é obtido de ADB e do processo do emulador; a imagem é disponibilizada pelo noVNC ligado ao display X que contém a janela do emulador. Se a imagem não existir ou o Android não arrancar, o painel deverá mostrar o diagnóstico em vez de inventar uma versão.

## 5. Limitações conhecidas

- Este repositório **não contém nem pode embutir** a imagem compilada do AOSP: vários gigabytes de artefactos precisam de ser gerados no host de build. Não foi feita aqui uma compilação/boot real.
- A configuração está direcionada para uma imagem `sdk_phone_x86_64` e para o layout dos artefactos dessa compilação. Confirme os logs da versão concreta do Android Emulator e ajuste o caminho da imagem se o host gerar um layout diferente.
- A experiência usa VNC sobre WebSocket, não um pipeline WebRTC dedicado. É adequada para acesso interativo, mas a latência e a taxa de frames dependem do servidor, rede e cliente. O áudio não está encaminhado.
- O envio de cliques/toques ocorre pela interação com a janela do emulador via noVNC; o painel também disponibiliza eventos de toque/deslize ADB. Gestos de hardware, sensores, câmara, telefonia e Google Play Services não são garantidos.
- O sistema é AOSP puro para o alvo selecionado. A disponibilidade de launcher, SystemUI, Definições e apps deve ser confirmada na imagem em execução; não se assume que inclua aplicações Google proprietárias.
- A execução integral no navegador através de WebAssembly não é apresentada como implementada porque não foi demonstrado o arranque completo dessa imagem num runtime WASM.

## 6. Árvore do projeto

```text
android12-browser-lab/
├── aosp-image/                 # artefactos compilados (gerados, não incluídos)
├── frontend/                   # painel/controlos; não imita aplicações Android
├── gateway/                    # Nginx, Basic Auth e proxy WebSocket
├── server/                     # FastAPI, Android Emulator, ADB, VNC
├── scripts/build-aosp-android12.sh
├── docker-compose.yml
└── .env.example
```
