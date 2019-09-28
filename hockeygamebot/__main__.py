import logging

from hockeygamebot import app

if __name__ == "__main__":
    game = app.run()

    # All necessary Objects are created, start the game loop!
    logging.info("Starting main game loop now!")
    app.start_game_loop(game)
