from main import UserIn, UserUpdate, service, verify_password


def main() -> None:
    users = service.users()
    existing = next((user for user in users if user.get("user_id") == "test01"), None)
    if existing:
        user = service.update_user(
            int(existing["id"]),
            UserUpdate(password="123456", username="测试用户"),
        )
    else:
        user = service.create_user(
            UserIn(user_id="test01", password="123456", username="测试用户"),
        )

    auth = service.authenticate("test01", "123456")
    if not auth.get("ok"):
        raise SystemExit("test01 login verification failed")

    users = service.users()
    refreshed = next(user for user in users if user.get("user_id") == "test01")
    if "password_hash" in refreshed and not verify_password("123456", refreshed["password_hash"]):
        raise SystemExit("test01 password hash verification failed")
    print("test01 is ready")


if __name__ == "__main__":
    main()
