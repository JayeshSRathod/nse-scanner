from nse_daily_runner import main
from github_push import push_json_to_github

if __name__ == "__main__":
    print("🚀 Running NSE Pipeline...")
    main()

    print("📤 Pushing JSON to GitHub...")
    push_json_to_github()

    print("✅ Pipeline + Upload completed")