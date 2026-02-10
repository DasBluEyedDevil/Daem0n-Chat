# macOS Code Signing & Notarization Guide

This guide walks you through obtaining and configuring the certificates needed to sign DaemonChat's macOS `.pkg` installer.

## Why Sign?

Without signing, macOS Gatekeeper will show users a warning: *"DaemonChat-1.0.0-arm64.pkg can't be opened because Apple cannot check it for malicious software."* Users can still install by right-clicking and selecting Open, but signing provides a much better experience.

## Prerequisites

- An **Apple Developer Program** membership ($99/year) at https://developer.apple.com/programs/
- A Mac with Xcode command-line tools installed (for certificate generation)

## Step 1: Create a Developer ID Installer Certificate

1. Go to https://developer.apple.com/account/resources/certificates/list
2. Click the **+** button to create a new certificate
3. Select **Developer ID Installer** (under the "Software" section)
4. Follow the prompts:
   - Open **Keychain Access** on your Mac
   - Go to **Keychain Access > Certificate Assistant > Request a Certificate From a Certificate Authority**
   - Fill in your email and select **Saved to disk**
   - Upload the generated `.certSigningRequest` file to the Apple Developer portal
5. Download the generated certificate (`.cer` file)
6. Double-click the `.cer` file to install it in your Keychain

## Step 2: Export as .p12

1. Open **Keychain Access**
2. Find your **Developer ID Installer** certificate (under "My Certificates")
3. Right-click > **Export...**
4. Choose **Personal Information Exchange (.p12)** format
5. Set a strong password (you'll need this for the GitHub secret)
6. Save the file

## Step 3: Base64-Encode the Certificate

In Terminal, run:

```bash
base64 -i YourCertificate.p12 | pbcopy
```

This copies the base64-encoded certificate to your clipboard.

## Step 4: Create an App-Specific Password for Notarization

1. Go to https://appleid.apple.com/account/manage
2. Sign in with your Apple ID
3. Under **Security** (or **Sign-In and Security**), find **App-Specific Passwords**
4. Click **Generate an app-specific password**
5. Name it "GitHub Actions Notarization" (or similar)
6. Copy the generated password

## Step 5: Configure GitHub Secrets

Go to your repository's **Settings > Secrets and variables > Actions** and add these secrets:

| Secret Name | Value | Description |
|---|---|---|
| `MACOS_INSTALLER_CERT_BASE64` | The base64-encoded `.p12` from Step 3 | Developer ID Installer certificate |
| `MACOS_INSTALLER_CERT_PASSWORD` | The password from Step 2 | Password used when exporting `.p12` |
| `KEYCHAIN_PASSWORD` | Any random password | Used to create a temporary keychain in CI |
| `APPLE_ID` | your@email.com | Your Apple ID email |
| `TEAM_ID` | Your 10-character Team ID | Found at https://developer.apple.com/account under Membership Details |
| `NOTARIZATION_PASSWORD` | The app-specific password from Step 4 | For `notarytool` authentication |

> **Note:** `TEAM_ID` and `KEYCHAIN_PASSWORD` may already be configured if you have the iOS TestFlight workflow set up. They can be reused.

## Step 6: Run the Workflow

1. Go to **Actions > Build macOS Installer** in your repository
2. Click **Run workflow**
3. Enter the version (default: `1.0.0`)
4. The workflow will:
   - Build `.pkg` installers for both arm64 and x86_64
   - Sign with your Developer ID Installer certificate
   - Submit for Apple notarization and wait for approval
   - Staple the notarization ticket to the `.pkg`
   - Upload signed + notarized `.pkg` files as artifacts

## Running Without Signing

If you don't configure the signing secrets, the workflow still works and produces **unsigned** `.pkg` files. Users will need to bypass Gatekeeper to install them:

1. Right-click (or Control-click) the `.pkg` file
2. Select **Open**
3. Click **Open** in the dialog

## Troubleshooting

### "No signing identity found"

The workflow couldn't find a "Developer ID Installer" identity in the imported certificate. Make sure:
- You exported a **Developer ID Installer** certificate (not "Apple Distribution" or "Developer ID Application")
- The `.p12` export included the private key (right-click the certificate under "My Certificates", not just "Certificates")

### Notarization fails

- Ensure the `APPLE_ID` and `TEAM_ID` match the account that owns the Developer ID certificate
- The `NOTARIZATION_PASSWORD` must be an **app-specific password**, not your Apple ID password
- Check notarization logs: `xcrun notarytool log <submission-id> --apple-id ... --team-id ... --password ...`

### "Developer ID Installer" vs "Developer ID Application"

- **Developer ID Installer**: Signs `.pkg` installer packages. This is what you need.
- **Developer ID Application**: Signs `.app` bundles and standalone executables. Not needed for DaemonChat since we distribute a `.pkg`, not a standalone `.app`.
