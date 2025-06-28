# Digital Shop Telegram Bot

A Telegram bot for selling digital files with instant delivery after payment confirmation.

## Features

- **Admin Panel**: Upload files, create products, manage orders
- **Payment Methods**: CashApp and cryptocurrency payments
- **Instant Delivery**: Files delivered immediately after payment confirmation
- **Test Mode**: Safe testing environment for @packoa
- **Secure File Storage**: Token-based download system

## Admin Commands

- `/start` - Access main menu
- Admin Panel → Add Product (upload files)
- Admin Panel → View Orders (manage payments)
- Admin Panel → Test Mode (create test purchases)

## Payment Information

- **CashApp**: $shonwithcash
- **Bitcoin**: bc1q9nc2clammklw8jtvmzfqxg4e9exlcc7ww7e64e
- **Litecoin**: LZXDSYuxo2XZroFMgdQPRxfi2vjV3ncq3r
- **Ethereum**: 0xf812b0466ea671B3FadC75E9624dFeFd507F22C8

## Support

Contact: @xenslol

## Deployment

This bot is configured for Railway deployment with automatic restarts and error handling.

### Environment Variables Required

- `TELEGRAM_TOKEN` - Your Telegram bot token

### Deployment Steps

1. Push code to GitHub repository
2. Connect repository to Railway
3. Add environment variables
4. Deploy and monitor logs

The bot will automatically handle file storage, database operations, and payment processing.