<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/drive/1pzrKpxy2jV1xfupxP2Dm2Mw2s0x7OEKp

## Run Locally

**Prerequisites:**  Node.js

1. Install dependencies:
   `npm install`
2. Set the `GEMINI_API_KEY` in [.env.local](.env.local) to your Gemini API key
3. Run the app:
   `npm run dev`

# Error fixes

If you already have nodejs installed run the following:
1. The "Clean Slate" Fix (Recommended)
The most reliable way to handle Node on Ubuntu is using NVM (Node Version Manager). This bypasses the broken system versions entirely.

Run these commands in order:

1. Install NVM
```shell
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
```

2. Reload your terminal config (or just close and reopen the terminal)
```shell
source ~/.bashrc
```

3. Install the latest stable Node
```shell
nvm install 20
```

4. Tell your system to use it by default
```shell
nvm use 20
nvm alias default 20
```
2. If you prefer to stay with apt
If you don't want to use NVM, you must use the NodeSource repository to get a modern version, as the standard Ubuntu ones are too old for Vite.


1. Remove the old version first
```shell
sudo apt-get purge nodejs npm -y
sudo apt-get autoremove -y
```
2. Add the NodeSource repo for Node 20
```shell
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
```

3. Install the modern version
```shell
sudo apt-get install -y nodejs
```
3. Verify the fix
After running either of the above, run:

```shell
node -v
```
It must say v20.x.x (or at least v18+).

One final step: Since you had a failed install, your node_modules might be corrupted with the wrong architecture/links. Clear them out and try again:

```shell
rm -rf node_modules package-lock.json
npm install
npm run dev
```
