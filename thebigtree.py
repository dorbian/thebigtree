# -------
# Voice of TheBigTree for the Elf Discord
# Owned by an everlasting Deity that will consume your ever living soul if you steal this.
# -------

import bigtree
import asyncio
import sys

def start():
    try:
        if bigtree.initialize():
            bigtree.bot.run(bigtree.token)
        else:
            print("❌ BigTree failed to initialize (see logs for details).")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n🌲 BigTree gracefully stopped by user.")
    except Exception as e:
        print(f"💥 Unhandled startup exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    start()
