# FROZEN -- do not modify. The build the tests and the acceptance corpus both use.
#
# .RECIPEPREFIX instead of a literal tab, so the recipe indentation survives any editor.
.RECIPEPREFIX = >
ASM = nasm
LD = ld
BUILD = build

all: $(BUILD)/sum

$(BUILD):
> mkdir -p $(BUILD)

$(BUILD)/sum: src/sum.asm | $(BUILD)
> $(ASM) -f elf64 -o $(BUILD)/sum.o src/sum.asm
> $(LD) -e _start -o $(BUILD)/sum $(BUILD)/sum.o

clean:
> rm -rf $(BUILD)

.PHONY: all clean
