# -------
# Voice of TheBigTree for the Elf Discord
# owned by an everlasting Deity that will consume your ever living soul if you steal this
import bigtree
import asyncio

def start():
    if bigtree.initialize():
        bigtree.bot.run(bigtree.token)

if __name__ == '__main__':
    start()
